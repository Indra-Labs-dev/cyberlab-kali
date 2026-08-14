"""Phase 23 -- minimal Job reconciliation sweep.

Both Job-creation orderings this project uses (see the P1.3 comments in
app/api/routes/jobs.py, app/scheduling/ticker.py, app/ai/orchestrator.py,
app/chains/service.py) crash-protect against ONE of the two possible
failure windows between "Job row exists" and "RQ actually has the job":
flush-then-enqueue-then-commit means a crash before commit rolls the Job
row back, leaving nothing to reconcile (the RQ entry, if it made it to
Redis, just no-ops harmlessly when execute_job() finds no matching Job
row). The window this module exists for is different and cannot be closed
by ordering alone: Redis itself can lose a job it already accepted (a
Redis restart with no persistence, TTL eviction, a worker process crash
mid-execution) -- Postgres and Redis are never one transaction, no matter
what order the two writes happen in.

This sweep is intentionally small: find Jobs stuck at QUEUED or RUNNING
well past any realistic tool duration with no corresponding entry left in
RQ, and resolve them to FAILED with a clear, honest error message. It is
NOT a distributed scheduler, has no retry/backoff logic of its own, and
never re-enqueues a Job automatically -- silently re-running a scan that
may have actually executed against a real target is a worse outcome than
asking a human to explicitly retry.
"""

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.sync_session import get_sync_session
from app.jobs.pubsub import publish_job_update
from app.jobs.queue import get_queue
from app.models.job import Job, JobStatus

logger = logging.getLogger("cyberlab.jobs.reconciliation")

# Deliberately generous: well past every tool's max_timeout in the Tool
# Registry (the longest, nikto's basic_web_scan profile, caps at 280s) --
# this must never fire against a job that is simply still legitimately
# running.
DEFAULT_STUCK_AFTER = timedelta(minutes=30)


def reconcile_stuck_jobs(session: Session, *, stuck_after: timedelta = DEFAULT_STUCK_AFTER) -> list[uuid.UUID]:
    """Idempotent by construction: once a Job is resolved to FAILED here, it
    is no longer QUEUED/RUNNING, so a repeated call (or the next scheduled
    tick) never touches it again. Returns the ids of every Job it resolved,
    for observability/testing -- an empty list is the expected, common case.
    """
    cutoff = datetime.now(timezone.utc) - stuck_after
    stmt = select(Job).where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]), Job.created_at < cutoff)
    candidates = list(session.execute(stmt).scalars())
    if not candidates:
        return []

    queue = get_queue()
    reconciled_ids: list[uuid.UUID] = []
    for job in candidates:
        # queue.fetch_job() checks RQ's own registries (queued/started/
        # finished/failed) by job id -- None means Redis has no memory of
        # this job at all, the actual "orphaned" signal. A Job whose RQ
        # entry still exists (e.g. genuinely still `started`) is left
        # alone entirely; only Job rows with nothing left in Redis are
        # eligible.
        rq_job = queue.fetch_job(str(job.id))
        if rq_job is not None:
            continue

        original_status = job.status.value
        job.status = JobStatus.FAILED
        job.error = (
            f"reconciliation: job was stuck at {original_status} for over "
            f"{int(stuck_after.total_seconds())}s with no corresponding queue entry "
            "(worker or queue failure) -- retry manually if the scan is still needed"
        )
        job.finished_at = datetime.now(timezone.utc)
        session.commit()
        publish_job_update(str(job.id), {"id": str(job.id), "status": JobStatus.FAILED.value, "error": job.error})
        logger.warning("reconciled orphaned job %s (was %s)", job.id, original_status)
        reconciled_ids.append(job.id)

    return reconciled_ids


def run_reconciliation_sweep(*, stuck_after: timedelta = DEFAULT_STUCK_AFTER) -> list[uuid.UUID]:
    """Self-opening entry point for the background thread and tests that
    don't need to drive a specific Session -- mirrors
    app/scheduling/ticker.py::run_due_schedules()'s own self-opening
    pattern."""
    session = get_sync_session()
    try:
        return reconcile_stuck_jobs(session, stuck_after=stuck_after)
    finally:
        session.close()


def start_reconciliation_thread(poll_interval_seconds: int, *, stuck_after: timedelta = DEFAULT_STUCK_AFTER) -> threading.Thread:
    """Starts the sweep as a daemon thread -- called once from
    app/jobs/worker.py, alongside the Phase 14 scheduler ticker and the
    Phase 15 intel sync thread. Same pattern (background thread in the
    existing worker process, no new service), not a new scheduler."""

    def _loop() -> None:
        logger.info("job reconciliation thread started (poll interval: %ss, stuck_after: %ss)", poll_interval_seconds, int(stuck_after.total_seconds()))
        while True:
            try:
                run_reconciliation_sweep(stuck_after=stuck_after)
            except Exception:  # noqa: BLE001 -- one bad sweep must not kill the loop
                logger.exception("job reconciliation sweep failed")
            time.sleep(poll_interval_seconds)

    thread = threading.Thread(target=_loop, name="job-reconciliation", daemon=True)
    thread.start()
    return thread
