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

from app.ai.orchestrator import advance_mission
from app.chains.service import advance_chain_run
from app.db.sync_session import get_sync_session
from app.jobs.pubsub import publish_job_update
from app.jobs.queue import get_queue
from app.models.job import Job, JobStatus
from app.models.mission import Mission, MissionStatus, MissionStep, MissionStepStatus
from app.models.mission_template import ChainRun, ChainRunStatus, ChainRunStep, ChainRunStepStatus

logger = logging.getLogger("cyberlab.jobs.reconciliation")

# Deliberately generous: well past every tool's max_timeout in the Tool
# Registry (the longest, nikto's basic_web_scan profile, caps at 280s) --
# this must never fire against a job that is simply still legitimately
# running.
DEFAULT_STUCK_AFTER = timedelta(minutes=30)

# Post-Phase-23 consolidation (D.2) -- unlike DEFAULT_STUCK_AFTER above,
# this is NOT about how long a *tool* may legitimately run: a Mission/
# ChainRun step that is genuinely still executing is excluded up front (see
# _mission_last_progress_at/_chain_run_last_progress_at's "in flight" check
# below), regardless of its age. This threshold instead bounds the brief,
# normal in-process gap between _advance_mission_locked()'s/
# _advance_chain_run_locked()'s two commits (resolving the finished step,
# then queueing the next one) -- milliseconds in the healthy case -- so it
# can stay far shorter than DEFAULT_STUCK_AFTER without risking a false
# positive.
DEFAULT_ORCHESTRATION_STUCK_AFTER = timedelta(minutes=5)

# Mirrors app/ai/orchestrator.py's own _JOB_TERMINAL_STATUSES /
# app/chains/service.py's own copy -- each module that needs this
# distinction defines it locally rather than sharing one import, same
# existing precedent (see both modules).
_JOB_TERMINAL_STATUSES = (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED)
_MISSION_LIVE_STATUSES = (MissionStatus.APPROVED, MissionStatus.RUNNING)
_CHAIN_RUN_LIVE_STATUSES = (ChainRunStatus.RUNNING,)


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


def _mission_last_progress_at(
    session: Session, mission: Mission, steps: list[MissionStep]
) -> tuple[bool, datetime | None]:
    """Returns (has_in_flight_step, last_progress_at).

    A step counts as "in flight" only when it is QUEUED and its Job has not
    yet reached a terminal status -- the one check that must never produce
    a false positive: a mission legitimately running a slow tool must never
    be touched here, no matter how long ago it started (see
    DEFAULT_ORCHESTRATION_STUCK_AFTER's docstring above -- this function is
    what makes that threshold safe to keep short). When nothing is in
    flight, last_progress_at is the latest known moment of real activity:
    the most recent terminal Job's finished_at among this mission's steps
    -- NOT a max() with mission.approved_at, which would stay "fresh"
    forever on a mission approved recently regardless of how stale its
    actual step progress is. mission.approved_at is used only as a
    fallback, for the one case where no step has ever produced a Job yet
    (the very first advance).
    """
    latest_job_finished_at: datetime | None = None
    for step in steps:
        if step.job_id is None:
            continue
        job = session.get(Job, step.job_id)
        if job is None:
            continue
        if step.status == MissionStepStatus.QUEUED and job.status not in _JOB_TERMINAL_STATUSES:
            return True, None
        if job.finished_at is not None and (latest_job_finished_at is None or job.finished_at > latest_job_finished_at):
            latest_job_finished_at = job.finished_at
    if latest_job_finished_at is not None:
        return False, latest_job_finished_at
    return False, mission.approved_at


def reconcile_stuck_missions(
    session: Session, *, stuck_after: timedelta = DEFAULT_ORCHESTRATION_STUCK_AFTER
) -> list[uuid.UUID]:
    """Detects Missions whose forward progress has stalled and nudges them.

    The signature this catches is what a crash/DB failure between
    queue.enqueue() succeeding and _advance_mission_locked()'s own second,
    final commit leaves behind (see the P1.3 commit/enqueue comments in
    app/ai/orchestrator.py): the step that just finished IS safely resolved
    -- that resolution has its own, separate, already-succeeded commit --
    but the *next* step was never queued and mission.status was never
    advanced, because that second transaction rolled back whole. Nothing
    about this Mission is visible to reconcile_stuck_jobs() above: no Job
    row was ever durably created for the next step, so there is nothing
    orphaned in the `jobs` table to find.

    Repaired by simply re-invoking advance_mission() -- the exact same,
    already-tested production function a healthy Job-completion hook would
    have called, never bespoke state mutation. This is deliberately safe to
    call even on a Mission that turns out not to be stuck: advance_mission()
    re-reads ground truth itself under its own `SELECT ... FOR UPDATE` lock
    and is a documented no-op for a terminal or genuinely-in-flight mission
    (see its own docstring) -- so a detection false positive here costs one
    wasted lock+read, never a duplicate Job or a second tool execution.
    """
    cutoff = datetime.now(timezone.utc) - stuck_after
    candidates = list(session.execute(select(Mission).where(Mission.status.in_(_MISSION_LIVE_STATUSES))).scalars())
    nudged: list[uuid.UUID] = []
    for mission in candidates:
        steps = list(
            session.execute(
                select(MissionStep).where(MissionStep.mission_id == mission.id).order_by(MissionStep.step_order)
            ).scalars()
        )
        in_flight, last_progress_at = _mission_last_progress_at(session, mission, steps)
        if in_flight or last_progress_at is None or last_progress_at >= cutoff:
            continue
        logger.warning(
            "reconciliation: mission %s appears stuck (status=%s, no progress since %s) -- re-invoking advance_mission()",
            mission.id,
            mission.status.value,
            last_progress_at.isoformat(),
        )
        advance_mission(mission.id)
        nudged.append(mission.id)
    return nudged


def _chain_run_last_progress_at(
    session: Session, run: ChainRun, steps: list[ChainRunStep]
) -> tuple[bool, datetime | None]:
    """Same reasoning as _mission_last_progress_at above -- ChainRun has no
    APPROVED-equivalent status (it goes straight to RUNNING at creation, see
    app/chains/service.py::create_chain_run), so run.created_at is the
    fallback anchor instead of Mission.approved_at, used only when no step
    has ever produced a Job yet."""
    latest_job_finished_at: datetime | None = None
    for step in steps:
        if step.job_id is None:
            continue
        job = session.get(Job, step.job_id)
        if job is None:
            continue
        if step.status == ChainRunStepStatus.QUEUED and job.status not in _JOB_TERMINAL_STATUSES:
            return True, None
        if job.finished_at is not None and (latest_job_finished_at is None or job.finished_at > latest_job_finished_at):
            latest_job_finished_at = job.finished_at
    if latest_job_finished_at is not None:
        return False, latest_job_finished_at
    return False, run.created_at


def reconcile_stuck_chain_runs(
    session: Session, *, stuck_after: timedelta = DEFAULT_ORCHESTRATION_STUCK_AFTER
) -> list[uuid.UUID]:
    """ChainRun analog of reconcile_stuck_missions() above -- same failure
    signature (a crash between _advance_chain_run_locked()'s two commits),
    same conservative repair (re-invoke advance_chain_run(), never bespoke
    state mutation), same safety argument for false positives."""
    cutoff = datetime.now(timezone.utc) - stuck_after
    candidates = list(session.execute(select(ChainRun).where(ChainRun.status.in_(_CHAIN_RUN_LIVE_STATUSES))).scalars())
    nudged: list[uuid.UUID] = []
    for run in candidates:
        steps = list(
            session.execute(
                select(ChainRunStep).where(ChainRunStep.chain_run_id == run.id).order_by(ChainRunStep.step_order)
            ).scalars()
        )
        in_flight, last_progress_at = _chain_run_last_progress_at(session, run, steps)
        if in_flight or last_progress_at is None or last_progress_at >= cutoff:
            continue
        logger.warning(
            "reconciliation: chain run %s appears stuck (status=%s, no progress since %s) -- re-invoking advance_chain_run()",
            run.id,
            run.status.value,
            last_progress_at.isoformat(),
        )
        advance_chain_run(run.id)
        nudged.append(run.id)
    return nudged


def run_reconciliation_sweep(
    *,
    stuck_after: timedelta = DEFAULT_STUCK_AFTER,
    orchestration_stuck_after: timedelta = DEFAULT_ORCHESTRATION_STUCK_AFTER,
) -> list[uuid.UUID]:
    """Self-opening entry point for the background thread and tests that
    don't need to drive a specific Session -- mirrors
    app/scheduling/ticker.py::run_due_schedules()'s own self-opening
    pattern. Each of the three sweeps below is isolated in its own try/
    except (same principle as the isolated hooks in app/jobs/tasks.py's
    execute_job() finally block): a bug in the Mission/ChainRun sweep must
    never prevent the original Job-orphan sweep from running, and vice
    versa. Returns reconcile_stuck_jobs()'s result, preserving this
    function's existing return contract -- Mission/ChainRun nudges are
    logged individually by their own functions above rather than folded
    into this return value.
    """
    session = get_sync_session()
    try:
        reconciled_jobs: list[uuid.UUID] = []
        try:
            reconciled_jobs = reconcile_stuck_jobs(session, stuck_after=stuck_after)
        except Exception:  # noqa: BLE001 -- isolated: must not block the sweeps below
            logger.exception("reconciliation: job sweep failed")

        try:
            reconcile_stuck_missions(session, stuck_after=orchestration_stuck_after)
        except Exception:  # noqa: BLE001 -- isolated: must not block the other sweeps
            logger.exception("reconciliation: mission sweep failed")

        try:
            reconcile_stuck_chain_runs(session, stuck_after=orchestration_stuck_after)
        except Exception:  # noqa: BLE001 -- isolated: must not block the other sweeps
            logger.exception("reconciliation: chain run sweep failed")

        return reconciled_jobs
    finally:
        session.close()


def start_reconciliation_thread(
    poll_interval_seconds: int,
    *,
    stuck_after: timedelta = DEFAULT_STUCK_AFTER,
    orchestration_stuck_after: timedelta = DEFAULT_ORCHESTRATION_STUCK_AFTER,
) -> threading.Thread:
    """Starts the sweep as a daemon thread -- called once from
    app/jobs/worker.py, alongside the Phase 14 scheduler ticker and the
    Phase 15 intel sync thread. Same pattern (background thread in the
    existing worker process, no new service), not a new scheduler."""

    def _loop() -> None:
        logger.info(
            "job reconciliation thread started (poll interval: %ss, stuck_after: %ss, orchestration_stuck_after: %ss)",
            poll_interval_seconds,
            int(stuck_after.total_seconds()),
            int(orchestration_stuck_after.total_seconds()),
        )
        while True:
            try:
                run_reconciliation_sweep(stuck_after=stuck_after, orchestration_stuck_after=orchestration_stuck_after)
            except Exception:  # noqa: BLE001 -- one bad sweep must not kill the loop
                logger.exception("job reconciliation sweep failed")
            time.sleep(poll_interval_seconds)

    thread = threading.Thread(target=_loop, name="job-reconciliation", daemon=True)
    thread.start()
    return thread
