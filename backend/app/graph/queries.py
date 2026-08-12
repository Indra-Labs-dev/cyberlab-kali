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

from app.models.asset import Asset
from app.models.finding import Finding
from app.models.graph_edge import GraphEdge

MAX_GRAPH_DEPTH = 3

VALID_NODE_TYPES = {"ASSET", "FINDING", "CVE", "SERVICE", "TECHNOLOGY"}

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
