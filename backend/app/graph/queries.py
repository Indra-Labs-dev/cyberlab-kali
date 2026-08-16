"""Phase 17 -- depth-limited, cycle-safe graph traversal. A single
recursive CTE over `graph_edges`, not a graph database: at CyberLab's
scale (hundreds of edges around any one Asset/Finding, never millions)
this is fast and keeps the whole system on one PostgreSQL instance.

Cycle safety: the CTE carries a `visited` text array of every node key
seen so far on the current path and refuses to step onto a node already
in it -- a real cycle (A -[REL]-> B -[REL]-> C -[REL]-> A, which the
Asset<->Asset RELATED_TO rule alone can already produce for 3+ assets
sharing a technology) terminates instead of looping forever. Verified in
tests/graph/test_queries.py with a real 3-node cycle.

Depth is never a free integer: `MAX_GRAPH_DEPTH` bounds it server-side
regardless of what a caller requests, so a traversal can never become an
unbounded/expensive query no matter the request.
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetCriticality
from app.models.finding import Finding
from app.models.graph_edge import GraphEdge

MAX_GRAPH_DEPTH = 3

VALID_NODE_TYPES = {"ASSET", "FINDING", "CVE", "SERVICE", "TECHNOLOGY"}

# Phase 24 -- Attack Path Analysis. One hop more than MAX_GRAPH_DEPTH on
# purpose: that constant was tuned for a *neighborhood* view meant to stay
# readable on screen (local_graph()), not for a *path* to a specific,
# possibly-distant node -- a real path (e.g. Asset -EXPOSES-> Service,
# Asset -USES_TECHNOLOGY-> Technology -RELATED_TO-> Asset -HAS_FINDING->
# Finding) can reasonably need one more hop than a "what's nearby" view.
MAX_ATTACK_PATH_HOPS = 4
# Hard ceiling on how many distinct paths a single request returns -- a
# human is expected to read and manually verify every path this endpoint
# returns (see module-level disclaimer in app/schemas/graph.py), so the
# cap is chosen for that, not for exhaustiveness. Shortest paths are kept
# first (see _shortest_first below) when more exist than this.
MAX_ATTACK_PATHS = 20
# Circuit breaker on the raw, pre-filter SQL row count -- CyberLab's own
# graph stays in the hundreds of edges (see this module's own docstring),
# so this is generous headroom, not a tuned production limit.
_MAX_RAW_PATH_ROWS = 2000

# Bidirectional traversal (see module docstring): a real edge is walkable
# from either endpoint when exploring "what's around this node", even
# though its `relation` label (HAS_FINDING, EXPOSES, ...) stays directional
# in the data itself -- direction is preserved in the edges returned to
# the caller, only the walk itself ignores it.
_TRAVERSAL_SQL = text(
    """
    WITH RECURSIVE bidirectional_edges AS (
        SELECT id, from_type, from_id, to_type, to_id
        FROM graph_edges
        UNION ALL
        SELECT id, to_type, to_id, from_type, from_id
        FROM graph_edges
    ),
    traversal AS (
        SELECT be.id, be.to_type, be.to_id, 1 AS hop,
               ARRAY[:seed_type || ':' || :seed_id, be.to_type || ':' || be.to_id] AS visited
        FROM bidirectional_edges be
        WHERE be.from_type = :seed_type AND be.from_id = :seed_id

        UNION ALL

        SELECT be.id, be.to_type, be.to_id, t.hop + 1,
               t.visited || ARRAY[be.to_type || ':' || be.to_id]
        FROM traversal t
        JOIN bidirectional_edges be ON be.from_type = t.to_type AND be.from_id = t.to_id
        WHERE t.hop < :max_depth
          AND NOT (be.to_type || ':' || be.to_id = ANY(t.visited))
    )
    SELECT DISTINCT id FROM traversal
    """
)


class InvalidDepthError(ValueError):
    pass


class UnknownNodeTypeError(ValueError):
    pass


async def local_graph(db: AsyncSession, node_type: str, node_id: str, depth: int) -> dict:
    """Returns every edge (and the nodes they touch) within `depth` hops of
    (node_type, node_id), regardless of walk direction. Always includes the
    seed node itself, even with zero edges (an Asset just created and never
    scanned still renders as a lone node, not an error).
    """
    if node_type not in VALID_NODE_TYPES:
        raise UnknownNodeTypeError(f"unknown node type: {node_type}")
    if depth < 1 or depth > MAX_GRAPH_DEPTH:
        raise InvalidDepthError(f"depth must be between 1 and {MAX_GRAPH_DEPTH}, got {depth}")

    edge_id_rows = (
        await db.execute(_TRAVERSAL_SQL, {"seed_type": node_type, "seed_id": node_id, "max_depth": depth})
    ).all()
    edge_ids = [row[0] for row in edge_id_rows]

    edges: list[dict] = []
    node_keys: set[tuple[str, str]] = {(node_type, node_id)}
    if edge_ids:
        rows = (await db.execute(select(GraphEdge).where(GraphEdge.id.in_(edge_ids)))).scalars().all()
        for e in rows:
            edges.append(
                {
                    "id": str(e.id),
                    "from_type": e.from_type,
                    "from_id": e.from_id,
                    "to_type": e.to_type,
                    "to_id": e.to_id,
                    "relation": e.relation,
                    "source": e.source,
                    "reason": e.reason,
                    "metadata": e.edge_metadata,
                }
            )
            node_keys.add((e.from_type, e.from_id))
            node_keys.add((e.to_type, e.to_id))

    nodes = await _hydrate_nodes(db, node_keys)
    return {"nodes": nodes, "edges": edges}


# Phase 24 -- Attack Path Analysis. Same bidirectional_edges + `visited`
# cycle-guard technique as _TRAVERSAL_SQL above, extended to also carry the
# ordered array of edge ids walked so far: local_graph() only needs "is
# this node reachable", this needs the actual route taken to get there.
_PATH_TRAVERSAL_SQL = text(
    """
    WITH RECURSIVE bidirectional_edges AS (
        SELECT id, from_type, from_id, to_type, to_id
        FROM graph_edges
        UNION ALL
        SELECT id, to_type, to_id, from_type, from_id
        FROM graph_edges
    ),
    traversal AS (
        SELECT be.id, be.to_type, be.to_id, 1 AS hop,
               ARRAY[be.id] AS path_edge_ids,
               ARRAY[:seed_type || ':' || :seed_id, be.to_type || ':' || be.to_id] AS visited
        FROM bidirectional_edges be
        WHERE be.from_type = :seed_type AND be.from_id = :seed_id

        UNION ALL

        SELECT be.id, be.to_type, be.to_id, t.hop + 1,
               t.path_edge_ids || ARRAY[be.id],
               t.visited || ARRAY[be.to_type || ':' || be.to_id]
        FROM traversal t
        JOIN bidirectional_edges be ON be.from_type = t.to_type AND be.from_id = t.to_id
        WHERE t.hop < :max_depth
          AND NOT (be.to_type || ':' || be.to_id = ANY(t.visited))
    )
    SELECT to_type, to_id, hop, path_edge_ids FROM traversal
    LIMIT :row_cap
    """
)

_ATTACK_PATH_DISCLAIMER = (
    "These are structural paths derived from the graph data collected so far -- not proof of "
    "real exploitability, and the graph is not guaranteed to represent the complete attack "
    "surface. Treat every path as a hypothesis that still needs manual verification."
)


async def _enumerate_paths(
    db: AsyncSession, seed_type: str, seed_id: str, max_hops: int
) -> list[tuple[str, str, int, list[uuid.UUID]]]:
    """Every distinct path (cycle-safe, bounded to max_hops) starting at
    the seed node, as raw (to_type, to_id, hop, path_edge_ids) rows. Bounded
    by _MAX_RAW_PATH_ROWS as a circuit breaker, not a tuned production
    limit -- see that constant's docstring. Callers filter by their own
    terminal-node predicate (a specific target, or "is a CRITICAL asset")
    since that's the one thing that differs between find_paths_between()
    and find_paths_to_critical_assets() below.
    """
    rows = (
        await db.execute(
            _PATH_TRAVERSAL_SQL,
            {"seed_type": seed_type, "seed_id": seed_id, "max_depth": max_hops, "row_cap": _MAX_RAW_PATH_ROWS},
        )
    ).all()
    return [(r[0], r[1], r[2], list(r[3])) for r in rows]


async def _build_paths_response(
    db: AsyncSession, seed_type: str, seed_id: str, matching_rows: list[tuple[str, str, int, list[uuid.UUID]]]
) -> dict:
    """Shared shaping for both attack-path functions below: caps to
    MAX_ATTACK_PATHS (shortest paths first -- a purely structural,
    objective ranking by hop count, never an exploitability/probability
    score), resolves each path's edge ids to real GraphEdge rows *in
    walked order* (not deduplicated into a single edge set the way
    local_graph() does -- a path is a specific ordered route, not a
    neighborhood), and hydrates every node touched via the same
    _hydrate_nodes() helper local_graph() already uses.
    """
    ranked = sorted(matching_rows, key=lambda row: row[2])
    truncated = len(ranked) > MAX_ATTACK_PATHS
    kept = ranked[:MAX_ATTACK_PATHS]

    all_edge_ids: set[uuid.UUID] = set()
    for _, _, _, path_edge_ids in kept:
        all_edge_ids.update(path_edge_ids)

    edges_by_id: dict[uuid.UUID, GraphEdge] = {}
    if all_edge_ids:
        rows = (await db.execute(select(GraphEdge).where(GraphEdge.id.in_(all_edge_ids)))).scalars().all()
        edges_by_id = {e.id: e for e in rows}

    def _edge_dict(e: GraphEdge) -> dict:
        return {
            "id": str(e.id),
            "from_type": e.from_type,
            "from_id": e.from_id,
            "to_type": e.to_type,
            "to_id": e.to_id,
            "relation": e.relation,
            "source": e.source,
            "reason": e.reason,
            "metadata": e.edge_metadata,
        }

    node_keys: set[tuple[str, str]] = {(seed_type, seed_id)}
    paths: list[dict] = []
    for _, _, hop, path_edge_ids in kept:
        ordered_edges = [edges_by_id[eid] for eid in path_edge_ids if eid in edges_by_id]
        # Walk from the seed, at each hop picking whichever endpoint of the
        # (direction-agnostic, see _TRAVERSAL_SQL's own comment above)
        # stored edge is NOT the node we're already standing on -- avoids
        # any assumption about from_type/from_id matching "the previous
        # node", which the bidirectional walk does not guarantee.
        node_sequence: list[tuple[str, str]] = [(seed_type, seed_id)]
        current = (seed_type, seed_id)
        for e in ordered_edges:
            endpoint_a, endpoint_b = (e.from_type, e.from_id), (e.to_type, e.to_id)
            next_node = endpoint_b if current == endpoint_a else endpoint_a
            node_sequence.append(next_node)
            node_keys.add(endpoint_a)
            node_keys.add(endpoint_b)
            current = next_node
        paths.append({"hops": hop, "node_keys": node_sequence, "edges": [_edge_dict(e) for e in ordered_edges]})

    nodes = await _hydrate_nodes(db, node_keys)
    nodes_by_key = {(n["type"], n["id"]): n for n in nodes}
    seed_node = nodes_by_key.get((seed_type, seed_id)) or {
        "id": seed_id,
        "type": seed_type,
        "label": seed_id,
        "metadata": {},
    }
    for p in paths:
        p["nodes"] = [nodes_by_key[k] for k in p.pop("node_keys")]

    return {"disclaimer": _ATTACK_PATH_DISCLAIMER, "seed": seed_node, "truncated": truncated, "paths": paths}


async def find_paths_to_critical_assets(
    db: AsyncSession, node_type: str, node_id: str, max_hops: int = MAX_ATTACK_PATH_HOPS
) -> dict:
    """Every path (cycle-safe, depth-bounded, count-capped) from the given
    node to a *different* Asset whose criticality is CRITICAL. If the seed
    is itself already a CRITICAL asset it is never counted as its own
    destination -- a 0-hop "path to yourself" is not a hypothesis worth
    reporting.
    """
    if node_type not in VALID_NODE_TYPES:
        raise UnknownNodeTypeError(f"unknown node type: {node_type}")
    if max_hops < 1 or max_hops > MAX_ATTACK_PATH_HOPS:
        raise InvalidDepthError(f"max_hops must be between 1 and {MAX_ATTACK_PATH_HOPS}, got {max_hops}")

    raw_rows = await _enumerate_paths(db, node_type, node_id, max_hops)
    candidate_ids = {to_id for to_type, to_id, _, _ in raw_rows if to_type == "ASSET" and (to_type, to_id) != (node_type, node_id)}

    critical_ids: set[str] = set()
    if candidate_ids:
        rows = (
            await db.execute(
                select(Asset.id).where(
                    Asset.id.in_(uuid.UUID(i) for i in candidate_ids), Asset.criticality == AssetCriticality.CRITICAL
                )
            )
        ).scalars().all()
        critical_ids = {str(i) for i in rows}

    matching = [row for row in raw_rows if row[0] == "ASSET" and row[1] in critical_ids]
    return await _build_paths_response(db, node_type, node_id, matching)


async def find_paths_between(
    db: AsyncSession, from_type: str, from_id: str, to_type: str, to_id: str, max_hops: int = MAX_ATTACK_PATH_HOPS
) -> dict:
    """Every path (cycle-safe, depth-bounded, count-capped) between two
    specific nodes. The same node on both ends is never a "path" -- there
    is nothing to traverse -- so this returns immediately with an empty
    path list rather than querying at all.
    """
    if from_type not in VALID_NODE_TYPES:
        raise UnknownNodeTypeError(f"unknown node type: {from_type}")
    if to_type not in VALID_NODE_TYPES:
        raise UnknownNodeTypeError(f"unknown node type: {to_type}")
    if max_hops < 1 or max_hops > MAX_ATTACK_PATH_HOPS:
        raise InvalidDepthError(f"max_hops must be between 1 and {MAX_ATTACK_PATH_HOPS}, got {max_hops}")

    if (from_type, from_id) == (to_type, to_id):
        return await _build_paths_response(db, from_type, from_id, [])

    raw_rows = await _enumerate_paths(db, from_type, from_id, max_hops)
    matching = [row for row in raw_rows if row[0] == to_type and row[1] == to_id]
    return await _build_paths_response(db, from_type, from_id, matching)


async def _hydrate_nodes(db: AsyncSession, node_keys: set[tuple[str, str]]) -> list[dict]:
    """Real nodes (ASSET/FINDING) are looked up in their actual tables for a
    real label/metadata; virtual nodes (CVE/SERVICE/TECHNOLOGY) use their
    external_id as both id and label -- there is nothing else to look up,
    they were never a row anywhere.
    """
    asset_ids = [uuid.UUID(nid) for ntype, nid in node_keys if ntype == "ASSET"]
    finding_ids = [uuid.UUID(nid) for ntype, nid in node_keys if ntype == "FINDING"]

    assets_by_id: dict[str, Asset] = {}
    if asset_ids:
        rows = (await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all()
        assets_by_id = {str(a.id): a for a in rows}

    findings_by_id: dict[str, Finding] = {}
    if finding_ids:
        rows = (await db.execute(select(Finding).where(Finding.id.in_(finding_ids)))).scalars().all()
        findings_by_id = {str(f.id): f for f in rows}

    nodes = []
    for ntype, nid in node_keys:
        if ntype == "ASSET":
            asset = assets_by_id.get(nid)
            nodes.append(
                {
                    "id": nid,
                    "type": "ASSET",
                    "label": asset.name if asset else nid,
                    "metadata": {"hostname": asset.hostname, "criticality": asset.criticality.value} if asset else {},
                }
            )
        elif ntype == "FINDING":
            finding = findings_by_id.get(nid)
            nodes.append(
                {
                    "id": nid,
                    "type": "FINDING",
                    "label": finding.title if finding else nid,
                    "metadata": (
                        {
                            "severity": finding.severity.value,
                            "status": finding.status.value,
                            "risk_score": finding.risk_score,
                            "risk_priority": finding.risk_priority.value if finding.risk_priority else None,
                        }
                        if finding
                        else {}
                    ),
                }
            )
        else:
            nodes.append({"id": nid, "type": ntype, "label": nid, "metadata": {}})
    return nodes
