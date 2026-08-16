import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.graph.queries import (
    MAX_ATTACK_PATH_HOPS,
    MAX_GRAPH_DEPTH,
    VALID_NODE_TYPES,
    find_paths_between,
    find_paths_to_critical_assets,
    local_graph,
)
from app.graph.service import run_graph_rebuild
from app.jobs.queue import get_queue
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.project import Project
from app.schemas.graph import AttackPathsResponse, GraphRebuildRequest, GraphRebuildTriggerResponse, GraphResponse

router = APIRouter(prefix="/graph", tags=["graph"])

# Bounds how many assets a single /projects/{id} response merges -- a
# project graph is meant for a human to actually read, not a full-database
# dump. See docs/phase-17-security-graph.md#performance for the real
# numbers this was checked against.
_MAX_PROJECT_ASSETS = 50


@router.get("/assets/{asset_id}", response_model=GraphResponse)
async def get_asset_graph(
    asset_id: uuid.UUID,
    depth: int = Query(default=1, ge=1, le=MAX_GRAPH_DEPTH),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    graph = await local_graph(db, "ASSET", str(asset_id), depth)
    return GraphResponse(**graph)


@router.get("/findings/{finding_id}", response_model=GraphResponse)
async def get_finding_graph(
    finding_id: uuid.UUID,
    depth: int = Query(default=1, ge=1, le=MAX_GRAPH_DEPTH),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    graph = await local_graph(db, "FINDING", str(finding_id), depth)
    return GraphResponse(**graph)


@router.get("/nodes/{node_type}/{node_id}", response_model=GraphResponse)
async def get_node_graph(
    node_type: str,
    node_id: str,
    depth: int = Query(default=1, ge=1, le=MAX_GRAPH_DEPTH),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    node_type = node_type.upper()
    if node_type not in VALID_NODE_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown node type: {node_type}")

    # ASSET/FINDING are real rows -- 404 like the dedicated routes above so
    # a typo'd/deleted ID doesn't silently return an empty-but-"valid" graph.
    # CVE/SERVICE/TECHNOLOGY are virtual (no backing table, see
    # app/models/graph_edge.py) -- an unknown one just has zero edges,
    # which is the honest answer, not a 404.
    if node_type == "ASSET":
        try:
            asset_uuid = uuid.UUID(node_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="asset not found") from None
        if await db.get(Asset, asset_uuid) is None:
            raise HTTPException(status_code=404, detail="asset not found")
    elif node_type == "FINDING":
        try:
            finding_uuid = uuid.UUID(node_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="finding not found") from None
        if await db.get(Finding, finding_uuid) is None:
            raise HTTPException(status_code=404, detail="finding not found")

    graph = await local_graph(db, node_type, node_id, depth)
    return GraphResponse(**graph)


@router.get("/projects/{project_id}", response_model=GraphResponse)
async def get_project_graph(
    project_id: uuid.UUID,
    depth: int = Query(default=1, ge=1, le=MAX_GRAPH_DEPTH),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    asset_ids = (
        await db.execute(
            select(Asset.id).where(Asset.project_id == project_id).order_by(Asset.created_at).limit(_MAX_PROJECT_ASSETS)
        )
    ).scalars().all()

    nodes_by_key: dict[tuple[str, str], dict] = {}
    edges_by_id: dict[str, dict] = {}
    for asset_id in asset_ids:
        graph = await local_graph(db, "ASSET", str(asset_id), depth)
        for node in graph["nodes"]:
            nodes_by_key[(node["type"], node["id"])] = node
        for edge in graph["edges"]:
            edges_by_id[edge["id"]] = edge

    return GraphResponse(nodes=list(nodes_by_key.values()), edges=list(edges_by_id.values()))


async def _ensure_node_exists(db: AsyncSession, node_type: str, node_id: str) -> str:
    """Same validation as get_node_graph() above, factored out for the two
    Phase 24 routes below -- ASSET/FINDING 404 on an unknown/malformed id
    (a typo'd/deleted id must never silently produce an empty-but-"valid"
    result), virtual types (CVE/SERVICE/TECHNOLOGY) never 404 since they
    have no backing table to check against. get_node_graph() itself is
    left untouched rather than refactored onto this helper -- no functional
    need to risk already-tested code for a cosmetic dedup.
    """
    node_type = node_type.upper()
    if node_type not in VALID_NODE_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown node type: {node_type}")
    if node_type == "ASSET":
        try:
            asset_uuid = uuid.UUID(node_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="asset not found") from None
        if await db.get(Asset, asset_uuid) is None:
            raise HTTPException(status_code=404, detail="asset not found")
    elif node_type == "FINDING":
        try:
            finding_uuid = uuid.UUID(node_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="finding not found") from None
        if await db.get(Finding, finding_uuid) is None:
            raise HTTPException(status_code=404, detail="finding not found")
    return node_type


@router.get("/attack-paths/critical/{node_type}/{node_id}", response_model=AttackPathsResponse)
async def get_attack_paths_to_critical_assets(
    node_type: str,
    node_id: str,
    max_hops: int = Query(default=MAX_ATTACK_PATH_HOPS, ge=1, le=MAX_ATTACK_PATH_HOPS),
    db: AsyncSession = Depends(get_db),
) -> AttackPathsResponse:
    """Phase 24 -- every potential path (bounded, capped, never a certainty)
    from this node to a CRITICAL-criticality Asset. See
    app/graph/queries.py::find_paths_to_critical_assets and the
    `disclaimer` field always present on the response.
    """
    node_type = await _ensure_node_exists(db, node_type, node_id)
    result = await find_paths_to_critical_assets(db, node_type, node_id, max_hops)
    return AttackPathsResponse(**result)


@router.get("/attack-paths/between/{from_type}/{from_id}/{to_type}/{to_id}", response_model=AttackPathsResponse)
async def get_attack_paths_between(
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    max_hops: int = Query(default=MAX_ATTACK_PATH_HOPS, ge=1, le=MAX_ATTACK_PATH_HOPS),
    db: AsyncSession = Depends(get_db),
) -> AttackPathsResponse:
    """Phase 24 -- every potential path (bounded, capped, never a certainty)
    between two explicitly chosen nodes. Mainly useful to validate the
    traversal engine itself against the graph's current, limited data (see
    app/graph/queries.py::find_paths_between) rather than only relying on
    the CRITICAL-asset search above.
    """
    from_type = await _ensure_node_exists(db, from_type, from_id)
    to_type = await _ensure_node_exists(db, to_type, to_id)
    result = await find_paths_between(db, from_type, from_id, to_type, to_id, max_hops)
    return AttackPathsResponse(**result)


@router.post("/rebuild", response_model=GraphRebuildTriggerResponse, status_code=202)
async def trigger_graph_rebuild(body: GraphRebuildRequest = GraphRebuildRequest()) -> GraphRebuildTriggerResponse:
    """Runs through the existing RQ queue, same substrate as a scan Job or
    the intelligence sync trigger (Phase 15) -- never inline in the
    request, and RQ's single-worker-at-a-time processing serializes
    concurrent rebuild requests for free (see app/graph/service.py::
    run_graph_rebuild). Idempotent: rebuilding twice never duplicates an
    edge (app/graph/builder.py upserts on the same unique key every time).
    """
    queue = get_queue()
    queue.enqueue(
        run_graph_rebuild,
        project_id=str(body.project_id) if body.project_id else None,
        asset_id=str(body.asset_id) if body.asset_id else None,
        job_timeout=300,
    )
    return GraphRebuildTriggerResponse(status="queued")
