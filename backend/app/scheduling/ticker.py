"""Phase 14 -- Continuous Recon ticker. Runs as a background thread inside
the `cyberlab-worker` process (see app/jobs/worker.py), not a new service:
the worker already has the sync DB access and Redis/RQ connection this
needs (the same ones app/jobs/tasks.py::execute_job uses).

Every tick: claim due ScheduledJobs (Postgres row-lock reservation, not a
Redis lock -- see claim_due_schedules), then for each one, run through
*exactly* the same authorization + Tool Registry validation as a manual
`POST /api/jobs` call (app.targets.authorization.is_executable +
app.jobs.service.prepare_job) before creating and enqueuing a Job. A
schedule never gets its own execution path.
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.sync_session import get_sync_session
from app.jobs.queue import get_queue
from app.jobs.service import prepare_job
from app.jobs.tasks import execute_job
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.models.scheduled_job import ScheduledJob, ScheduledJobStatus
from app.targets.authorization import is_executable
from app.tools import registry

logger = logging.getLogger("cyberlab.scheduler")

# Caps how many schedules a single tick claims -- an idle-stack safety
# valve, not expected to matter at the scale of a local single-user tool.
_BATCH_SIZE = 50

# A schedule that fails to even produce a Job (asset gone/unauthorized, tool
# no longer valid) this many ticks in a row is auto-paused rather than
# retried forever -- "NE PAS faire une boucle infinie". A human has to
# explicitly resume it once the underlying issue is fixed.
MAX_CONSECUTIVE_FAILURES = 5


def claim_due_schedules(session: Session) -> list[ScheduledJob]:
    """Reserves due schedules by advancing next_run_at *before* doing any
    work, inside one short transaction protected by `FOR UPDATE SKIP
    LOCKED`. This is the Postgres-native reservation the spec asks for
    instead of a Redis lock: even if two ticker threads/processes ran this
    concurrently (there is only one today, in-process in the worker, but the
    query is safe regardless), each due row is claimed by exactly one of
    them, and a crash between claiming and processing simply costs one
    missed run -- the row is not stuck, it fires again next interval.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(ScheduledJob)
        .where(ScheduledJob.status == ScheduledJobStatus.ACTIVE, ScheduledJob.next_run_at <= now)
        .order_by(ScheduledJob.next_run_at)
        .limit(_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    due = list(session.execute(stmt).scalars())
    for schedule in due:
        schedule.next_run_at = now + timedelta(seconds=schedule.interval_seconds)
    session.commit()
    return due


def _fail(session: Session, schedule: ScheduledJob, reason: str) -> None:
    schedule.consecutive_failures += 1
    schedule.last_error = reason
    if schedule.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        schedule.status = ScheduledJobStatus.PAUSED
        logger.warning(
            "scheduled_job %s auto-paused after %d consecutive failures: %s",
            schedule.id,
            schedule.consecutive_failures,
            reason,
        )
    session.commit()


def process_schedule(session: Session, schedule: ScheduledJob) -> None:
    """Turns one already-claimed, due ScheduledJob into a real Job, or
    records why it couldn't. Never raises -- a bad schedule must not stop
    the rest of the tick or crash the ticker thread.
    """
    try:
        if schedule.asset_id is None:
            _fail(session, schedule, "asset no longer exists")
            return

        asset = session.get(Asset, schedule.asset_id)
        if asset is None:
            schedule.status = ScheduledJobStatus.DISABLED
            schedule.last_error = "asset no longer exists"
            session.commit()
            return

        # Same enforcement as POST /api/jobs -- if authorization was revoked
        # since the schedule was created, the run is refused, not silently
        # downgraded or bypassed. The schedule stays ACTIVE: authorization
        # can be restored later, this is a transient refusal, not a
        # permanent one.
        if not is_executable(asset):
            _fail(session, schedule, f"asset authorization status is {asset.authorization_status.value}")
            return

        try:
            prepared = prepare_job(schedule.tool, schedule.profile, schedule.params, asset.address)
        except (registry.ToolNotFoundError, registry.ToolValidationError) as exc:
            _fail(session, schedule, str(exc))
            return

        job = Job(
            tool=schedule.tool,
            profile=schedule.profile,
            target=asset.address,
            project_id=asset.project_id,
            target_id=asset.id,
            params=prepared.full_params,
            status=JobStatus.QUEUED,
        )
        session.add(job)
        # Phase 23 -- flush (not commit) before enqueue, matching
        # app/api/routes/jobs.py, app/ai/orchestrator.py, and
        # app/chains/service.py: see the comment in routes/jobs.py for the
        # full reasoning on why this ordering, not the reverse, is used
        # consistently across all 4 Job-creation call sites.
        session.flush()

        queue = get_queue()
        queue.enqueue(
            execute_job,
            str(job.id),
            schedule.tool,
            prepared.full_params,
            prepared.effective_timeout,
            job_id=str(job.id),
            job_timeout=prepared.effective_timeout + 30,
        )

        schedule.last_run_at = datetime.now(timezone.utc)
        schedule.last_job_id = job.id
        schedule.consecutive_failures = 0
        schedule.last_error = None
        session.commit()
    except Exception as exc:  # noqa: BLE001 -- a scheduling bug must never take down the ticker thread
        session.rollback()
        logger.exception("scheduled_job %s failed to process: %s", schedule.id, exc)


def run_due_schedules() -> int:
    """One tick: claim + process. Returns how many schedules were handled
    (tests call this directly rather than waiting on the background loop).
    """
    session = get_sync_session()
    try:
        due = claim_due_schedules(session)
        for schedule in due:
            process_schedule(session, schedule)
        return len(due)
    finally:
        session.close()


def start_scheduler_thread(poll_interval_seconds: int) -> threading.Thread:
    """Starts the tick loop as a daemon thread. Called once from
    app/jobs/worker.py alongside the RQ Worker.work() loop -- both run in
    the same `cyberlab-worker` process/container, no new service.
    """

    def _loop() -> None:
        logger.info("scheduler ticker started (poll interval: %ss)", poll_interval_seconds)
        while True:
            try:
                run_due_schedules()
            except Exception:  # noqa: BLE001 -- one bad tick must not kill the loop
                logger.exception("scheduler tick failed")
            time.sleep(poll_interval_seconds)

    thread = threading.Thread(target=_loop, name="scheduler-ticker", daemon=True)
    thread.start()
    return thread
