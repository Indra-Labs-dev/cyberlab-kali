"""Phase 18 -- Mission lifecycle orchestrator (autonomy Level 2: "execute an
approved plan, one re-validated step at a time"). This is NOT the Tool
Orchestrator planned for Phase 21 (conditional multi-tool chaining) -- here
a Mission's step list is fixed at creation time by `AIMissionPlanner`
(unchanged, reused as-is) and advance_mission() only walks that fixed list
forward, creating one real `Job` per step through the exact same Policy
Engine gate everything else uses.

Deliberately split async/sync, mirroring the split app/jobs/service.py's own
module docstring already documents for prepare_job()/is_executable(), and
deliberately module-level functions for the sync half -- not methods on
`MissionOrchestrator` -- mirroring app/scheduling/ticker.py, which has no
class at all, just module functions:

- `MissionOrchestrator.create_mission()` is async: it only reads a target
  and calls AIMissionPlanner.plan() (network I/O to the AI provider), no
  locking, no Job creation -- so it runs directly on the API route's own
  AsyncSession, exactly like POST /api/ai/plan already does today. It is
  the only piece that needs an AIProvider, which is why it alone is a
  method on a class instead of a plain function.
- `approve_mission()` / `advance_mission()` / `cancel_mission()` are sync,
  module-level functions: they never touch the AI provider, only lock a
  Mission row and, when advancing, create a real Job through
  `app.jobs.service.prepare_job()` + `app.targets.authorization.is_executable()`
  -- the same two pure functions app/scheduling/ticker.py::process_schedule
  already uses as an independent, sync caller. This module is a third such
  caller, not a fourth job-creation mechanism: `app/jobs/service.py` and
  `app/api/routes/jobs.py` are untouched by this phase. These three
  functions are callable both from the async API route (via
  `asyncio.to_thread`, the same idiom app/api/routes/assets.py already uses
  for app.risk.service.recalculate_findings_for_asset_sync) and directly
  from app/jobs/tasks.py::execute_job, which is itself fully synchronous.

Locking: advance_mission() takes a blocking `SELECT ... FOR UPDATE` on the
Mission row -- deliberately NOT `SKIP LOCKED` (contrast with
ticker.py::claim_due_schedules, which locks a *batch* of independent,
skippable ScheduledJob rows). A concurrent second call for the same Mission
must wait for the first to commit, then re-read the now-current state and
become a no-op (see `_advance_mission_locked`'s early-return branches) --
never skip past a Mission it should actually act on, and never create a
second Job for the same step.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.planner import AIMissionPlanner
from app.ai.provider import AIProvider
from app.db.sync_session import get_sync_session
from app.jobs.queue import get_queue
from app.jobs.service import prepare_job
from app.jobs.tasks import execute_job
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.models.mission import Mission, MissionStatus, MissionStep, MissionStepStatus
from app.targets.authorization import is_executable
from app.tools import registry

logger = logging.getLogger("cyberlab.ai.orchestrator")

_TERMINAL_MISSION_STATUSES = (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED)
_JOB_TERMINAL_STATUSES = (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED)


class MissionNotFoundError(Exception):
    pass


class InvalidMissionStateError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stop_mission(session: Session, mission: Mission, status: MissionStatus) -> Mission:
    mission.status = status
    mission.finished_at = _now()
    session.commit()
    return mission


def _advance_mission_locked(session: Session, mission_id: uuid.UUID) -> Mission:
    """The testable, session-explicit core of advance_mission() -- takes an
    already-open sync Session so tests can drive two real, concurrent
    sessions against it directly (mirroring
    tests/scheduling/test_ticker.py::test_concurrent_claim_skip_locked_prevents_double_claim).
    Public callers go through `MissionOrchestrator.advance_mission()`, which
    opens/closes its own session around this function.
    """
    # 1+2: lock the Mission row (blocking, not skip_locked) and read its
    # current, possibly-just-changed-by-a-racing-call state.
    mission = session.execute(
        select(Mission).where(Mission.id == mission_id).with_for_update()
    ).scalar_one_or_none()
    if mission is None:
        raise MissionNotFoundError(str(mission_id))

    # 3-5: a terminal Mission is a no-op, not an error -- this is exactly
    # what makes a second/racing/retried call idempotent.
    if mission.status in _TERMINAL_MISSION_STATUSES:
        return mission

    steps = list(
        session.execute(
            select(MissionStep).where(MissionStep.mission_id == mission.id).order_by(MissionStep.step_order)
        ).scalars()
    )

    # Reconcile a QUEUED step against its Job's real outcome first -- this
    # is what actually makes progression happen: execute_job() never writes
    # to MissionStep itself, it only calls advance_mission_for_job() after
    # the Job's own status is already terminal, and this is the one place
    # that turns "Job finished" into "MissionStep finished". Without this,
    # a step would stay QUEUED forever and the mission would never progress
    # past its first step.
    queued_step = next((s for s in steps if s.status == MissionStepStatus.QUEUED), None)
    if queued_step is not None:
        job = session.get(Job, queued_step.job_id)
        if job is None or job.status not in _JOB_TERMINAL_STATUSES:
            return mission  # still running (or the Job row vanished) -- check again later
        if job.status == JobStatus.SUCCESS:
            queued_step.status = MissionStepStatus.SUCCESS
        elif job.status == JobStatus.CANCELLED:
            # The Job was cancelled directly (POST /api/jobs/{id}/cancel),
            # not via cancel_mission() -- still stops the mission, but as
            # CANCELLED, not FAILED, since nothing actually errored.
            queued_step.status = MissionStepStatus.CANCELLED
        else:
            queued_step.status = MissionStepStatus.FAILED
        session.commit()

    if any(s.status == MissionStepStatus.CANCELLED for s in steps):
        if mission.status != MissionStatus.CANCELLED:
            return _stop_mission(session, mission, MissionStatus.CANCELLED)
        return mission

    # Stop-on-failure, no retry in this phase: once any step has
    # FAILED/SKIPPED, the mission itself is FAILED and stays that way.
    if any(s.status in (MissionStepStatus.FAILED, MissionStepStatus.SKIPPED) for s in steps):
        if mission.status != MissionStatus.FAILED:
            return _stop_mission(session, mission, MissionStatus.FAILED)
        return mission

    # 6+7: max_steps is a hard cap independent of what the model proposed,
    # enforced here regardless of how many MissionStep rows exist --
    # defense in depth alongside the truncation already done at creation
    # time in create_mission().
    next_step = next(
        (s for s in steps if s.status == MissionStepStatus.PENDING and s.step_order < mission.max_steps), None
    )
    if next_step is None:
        # No more executable steps: COMPLETED only if at least one step
        # actually succeeded -- an all-skipped/all-capped mission is not a
        # success.
        final_status = (
            MissionStatus.COMPLETED if any(s.status == MissionStepStatus.SUCCESS for s in steps) else MissionStatus.FAILED
        )
        return _stop_mission(session, mission, final_status)

    if next_step.tool is None:
        # The planner already nulled this out (hallucinated / non-ai_allowed
        # tool, see AIMissionPlanner.plan) -- nothing to execute. SKIPPED
        # (not FAILED): ck_mission_step_job_id_required_when_executed
        # requires a job_id for FAILED/SUCCESS/QUEUED, and no Job was ever
        # attempted here -- SKIPPED is the correct terminal state for "this
        # step was never even attempted", the same reason it's used below
        # for a revoked authorization.
        next_step.status = MissionStepStatus.SKIPPED
        next_step.skip_reason = "step has no valid tool (rejected by the AI safety filter)"
        return _stop_mission(session, mission, MissionStatus.FAILED)

    # 8-10: re-verify authorization NOW, at execution time -- never trust
    # the authorization status the target had when the mission was
    # approved. Reload the Asset server-side; target_id itself is fixed at
    # Mission creation and is never replaced by anything the model outputs.
    asset = session.get(Asset, mission.target_id)
    if asset is None or not is_executable(asset):
        # 11: SKIPPED, never a Job -- and the mission stops, since every
        # remaining step targets the same now-unauthorized asset.
        next_step.status = MissionStepStatus.SKIPPED
        next_step.skip_reason = (
            "asset no longer exists" if asset is None else f"asset authorization status is {asset.authorization_status.value}"
        )
        return _stop_mission(session, mission, MissionStatus.FAILED)

    # 12: prepare -- the exact same pure function ticker.py uses, never a
    # parallel reimplementation of Tool Registry validation.
    try:
        prepared = prepare_job(next_step.tool, next_step.profile, next_step.options, asset.address)
    except (registry.ToolNotFoundError, registry.ToolValidationError) as exc:
        # SKIPPED for the same reason as above: no Job exists to attach,
        # so FAILED would violate ck_mission_step_job_id_required_when_executed.
        next_step.status = MissionStepStatus.SKIPPED
        next_step.skip_reason = str(exc)
        return _stop_mission(session, mission, MissionStatus.FAILED)

    job = Job(
        tool=next_step.tool,
        profile=next_step.profile,
        target=asset.address,
        project_id=asset.project_id,
        target_id=asset.id,
        params=prepared.full_params,
        status=JobStatus.QUEUED,
    )
    session.add(job)
    session.flush()  # need job.id before linking the step and enqueuing

    # 13: enqueue -- same RQ call, same job_timeout margin, as every other
    # job-creation path (POST /api/jobs, ticker.py::process_schedule).
    queue = get_queue()
    queue.enqueue(
        execute_job,
        str(job.id),
        next_step.tool,
        prepared.full_params,
        prepared.effective_timeout,
        job_id=str(job.id),
        job_timeout=prepared.effective_timeout + 30,
    )

    # 14-16.
    next_step.job_id = job.id
    next_step.status = MissionStepStatus.QUEUED
    mission.status = MissionStatus.RUNNING

    # 17: commit.
    session.commit()
    return mission


class MissionOrchestrator:
    def __init__(self, provider: AIProvider) -> None:
        self._planner = AIMissionPlanner(provider)

    async def create_mission(self, db, target: Asset, goal: str, max_steps: int = 10) -> Mission:
        """Async: called directly by the API route with its own AsyncSession
        and an already-loaded, already-404-checked Asset (the route owns
        that lookup, exactly like POST /api/ai/plan does today) -- this
        method never resolves target_id itself, so it can never be tricked
        into acting on an id the model invented.

        Permissive on purpose: a DRAFT mission may be created against a
        currently-unauthorized asset (authorization can be fixed before
        approval) -- the hard, re-checked-every-step gate is
        advance_mission()'s is_executable() call, not this one. This
        mirrors POST /api/ai/plan, which never blocks on authorization
        either.
        """
        plan = await self._planner.plan(
            target.address, goal, target_id=target.id, authorization_status=target.authorization_status.value
        )

        mission = Mission(
            project_id=target.project_id,
            target_id=target.id,
            goal=goal,
            status=MissionStatus.DRAFT,
            max_steps=max_steps,
            raw_response=plan.raw_response,
        )
        db.add(mission)
        await db.flush()

        # Hard cap applied here too (defense in depth -- see the identical
        # check in _advance_mission_locked): only the first max_steps
        # proposed steps are ever persisted, regardless of plan length.
        for order, step in enumerate(plan.steps[:max_steps]):
            db.add(
                MissionStep(
                    mission_id=mission.id,
                    step_order=order,
                    label=step.label,
                    tool=step.tool,
                    profile=step.profile,
                    options=step.options,
                    rationale=step.rationale,
                    status=MissionStepStatus.PENDING,
                )
            )

        await db.commit()
        await db.refresh(mission)
        return mission


def approve_mission(mission_id: uuid.UUID) -> Mission:
    """Sync, self-opening, module-level (not a MissionOrchestrator method --
    unlike create_mission(), this never touches the AI provider, so it needs
    no instance to call). DRAFT -> APPROVED, then immediately triggers the
    first advance_mission() call (a Mission never auto-starts on its own --
    approval is the one and only human action that starts execution).
    Callable both from the API route (via asyncio.to_thread) and, for
    approve, only ever from there -- execute_job()'s hook calls
    advance_mission() directly, never approve_mission().
    """
    session = get_sync_session()
    try:
        mission = session.execute(
            select(Mission).where(Mission.id == mission_id).with_for_update()
        ).scalar_one_or_none()
        if mission is None:
            raise MissionNotFoundError(str(mission_id))
        if mission.status != MissionStatus.DRAFT:
            raise InvalidMissionStateError(f"mission is {mission.status.value}, expected DRAFT")
        mission.status = MissionStatus.APPROVED
        mission.approved_at = _now()
        session.commit()
    finally:
        session.close()

    return advance_mission(mission_id)


def advance_mission(mission_id: uuid.UUID) -> Mission:
    """Sync, self-opening, module-level -- the entry point used both by the
    API route (via asyncio.to_thread) and by execute_job()'s
    post-completion hook (app/jobs/tasks.py), strictly after that job's own
    session/try-except has already closed -- see that module for why.
    """
    session = get_sync_session()
    try:
        return _advance_mission_locked(session, mission_id)
    finally:
        session.close()


def cancel_mission(mission_id: uuid.UUID) -> Mission:
    """Human kill switch, module-level. Never touches an in-flight Job --
    that stays the job of the existing POST /api/jobs/{id}/cancel;
    cancelling a Mission only prevents any *future* step from ever being
    queued.
    """
    session = get_sync_session()
    try:
        mission = session.execute(
            select(Mission).where(Mission.id == mission_id).with_for_update()
        ).scalar_one_or_none()
        if mission is None:
            raise MissionNotFoundError(str(mission_id))
        if mission.status in _TERMINAL_MISSION_STATUSES:
            return mission  # no-op on an already-terminal mission
        mission.status = MissionStatus.CANCELLED
        mission.finished_at = _now()
        session.commit()
        return mission
    finally:
        session.close()


def advance_mission_for_job(job_id: uuid.UUID | str) -> None:
    """Called by app/jobs/tasks.py::execute_job() strictly after that job's
    own session has already been closed and its terminal status (SUCCESS/
    FAILED/CANCELLED) already committed -- never before, and never sharing
    that session, so a Mission-side problem here can never retroactively
    flip an already-persisted Job back to FAILED. Callers must wrap this in
    their own try/except (execute_job's does) since it deliberately doesn't
    swallow errors itself -- the isolation guarantee is about *ordering and
    session separation*, not about hiding bugs.

    A Job that isn't part of any Mission (the overwhelming majority: manual
    POST /api/jobs runs, Phase 14 scheduled runs) is a cheap no-op -- one
    indexed lookup on mission_steps.job_id, nothing else.
    """
    session = get_sync_session()
    try:
        step = session.execute(select(MissionStep).where(MissionStep.job_id == job_id)).scalar_one_or_none()
        if step is None:
            return
        _advance_mission_locked(session, step.mission_id)
    finally:
        session.close()
