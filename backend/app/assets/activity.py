"""Phase 13 -- keeps Asset.first_seen/last_seen/technologies grounded in
real Job activity. These fields are deliberately never part of
AssetCreateRequest/AssetUpdateRequest (see app/schemas/asset.py): they are
observations, not user input, and are only ever written from here, called
by app/jobs/tasks.py::execute_job() once a job reaches a terminal state.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.asset import Asset


def record_asset_activity(
    session: Session,
    asset_id: uuid.UUID,
    observed_at: datetime,
    technologies: list[str] | None = None,
) -> None:
    """Update first_seen/last_seen for the asset a job just ran against, and
    merge in any newly observed technologies. No-op if the asset no longer
    exists (deleted between job creation and completion).
    """
    asset = session.get(Asset, asset_id)
    if asset is None:
        return

    if asset.first_seen is None or observed_at < asset.first_seen:
        asset.first_seen = observed_at
    if asset.last_seen is None or observed_at > asset.last_seen:
        asset.last_seen = observed_at

    if technologies:
        merged = set(asset.technologies or []) | set(technologies)
        asset.technologies = sorted(merged)


def technologies_from_whatweb(parsed: dict) -> list[str]:
    """Same plugin-name extraction as
    app/findings/extractor.py::extract_from_whatweb, reused here rather than
    re-parsing raw output a second time."""
    names: set[str] = set()
    for result in parsed.get("results", []):
        names.update(result.get("plugins", {}).keys())
    return sorted(names)
