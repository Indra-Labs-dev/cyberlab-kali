"""Phase 17 -- full/scoped Security Graph reconstruction, used by
`POST /api/graph/rebuild` and available for a from-scratch rebuild after
manually editing data or recovering from an incident. Thin wrapper around
app/graph/builder.py::build_graph_for_asset -- the actual edge-derivation
rules live there, this module only decides *which* assets to rebuild.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.sync_session import get_sync_session
from app.graph.builder import build_graph_for_asset
from app.models.asset import Asset


def rebuild_graph(session: Session, *, project_id: uuid.UUID | None = None, asset_id: uuid.UUID | None = None) -> int:
    """Rebuilds edges for one asset, every asset in one project, or every
    asset in the system (in that order of preference). Idempotent -- safe
    to call repeatedly, never produces duplicate edges. Returns the number
    of assets processed. Does not commit; the caller owns the transaction.
    """
    stmt = select(Asset)
    if asset_id is not None:
        stmt = stmt.where(Asset.id == asset_id)
    elif project_id is not None:
        stmt = stmt.where(Asset.project_id == project_id)

    assets = list(session.execute(stmt).scalars())
    for asset in assets:
        build_graph_for_asset(session, asset)
    return len(assets)


def run_graph_rebuild(project_id: str | None = None, asset_id: str | None = None) -> None:
    """RQ entrypoint for `POST /api/graph/rebuild` -- runs through the
    existing job queue (same substrate as a scan Job or the Phase 15 intel
    sync trigger), never inline in the request. This also serializes
    rebuilds for free: RQ's default worker processes one job at a time, so
    two rapid rebuild requests never race each other -- no separate lock
    needed on top of that.
    """
    session = get_sync_session()
    try:
        rebuild_graph(
            session,
            project_id=uuid.UUID(project_id) if project_id else None,
            asset_id=uuid.UUID(asset_id) if asset_id else None,
        )
        session.commit()
    finally:
        session.close()
