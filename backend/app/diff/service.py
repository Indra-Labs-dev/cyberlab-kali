"""Persists Diff Engine output as AssetChangeEvent rows. Called from
app/jobs/tasks.py::execute_job() once a job tied to an asset succeeds --
same sync Session as the rest of that function (see app/db/sync_session.py).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.diff.engine import SUPPORTED_TOOLS, diff_results
from app.models.asset_change_event import AssetChangeEvent
from app.models.job import Job, JobStatus

# How many recent comparable jobs to scan before giving up -- caps the query
# instead of loading an asset's entire scan history (Phase 14 performance
# requirement: compare only against the most recent compatible job).
_LOOKBACK_LIMIT = 20


def find_previous_comparable_job(session: Session, job: Job) -> Job | None:
    """Most recent prior SUCCESS job against the same asset, with the same
    tool/profile/params -- the Phase 14 "baseline" a new job is diffed
    against. Returns None if no such job exists (this job establishes the
    baseline instead)."""
    if job.target_id is None:
        return None

    stmt = (
        select(Job)
        .where(
            Job.target_id == job.target_id,
            Job.tool == job.tool,
            Job.status == JobStatus.SUCCESS,
            Job.id != job.id,
            Job.created_at < job.created_at,
        )
        .order_by(Job.created_at.desc())
        .limit(_LOOKBACK_LIMIT)
    )
    for candidate in session.execute(stmt).scalars():
        if candidate.profile == job.profile and candidate.params == job.params:
            return candidate
    return None


def generate_change_events(session: Session, job: Job) -> list[AssetChangeEvent]:
    """Diffs `job` against its most recent comparable predecessor and
    persists the resulting AssetChangeEvent rows (added to the session, not
    committed -- the caller, execute_job(), commits once for the whole
    terminal-state transition). No-op if the tool isn't diff-able, if there
    is no baseline yet, or if either result failed to parse."""
    if job.tool not in SUPPORTED_TOOLS or job.target_id is None or not job.result:
        return []

    previous = find_previous_comparable_job(session, job)
    if previous is None or not previous.result:
        return []

    raw_changes = diff_results(job.tool, previous.result, job.result)
    events = [
        AssetChangeEvent(
            asset_id=job.target_id,
            job_id=job.id,
            previous_job_id=previous.id,
            **change,
        )
        for change in raw_changes
    ]
    session.add_all(events)
    return events
