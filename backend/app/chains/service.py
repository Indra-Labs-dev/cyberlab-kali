"""Phase 21 -- Tool Orchestrator: deterministic, human-authored job
chaining. Sync, module-level functions -- mirrors app/ai/orchestrator.py's
Phase 18 pattern (approve_mission/advance_mission/cancel_mission) and
app/ai/memory.py's Phase 19 pattern (regenerate_project_summary), NOT a
class, and deliberately NOT under app/ai/: a `MissionTemplate` has no AI
involvement at all (no provider, no async call anywhere in this module) --
a human authors the template once, ahead of time, and starting a run
against a target is itself the human's deliberate action. There is no
separate DRAFT/APPROVED review step the way Phase 18's Mission needs one
(an AI-proposed plan needs review before it runs; a template a human
already wrote does not).

`advance_chain_run()` is the 4th independent sync caller of
`is_executable()` + `prepare_job()` in this codebase -- after
`app/api/routes/jobs.py::create_job` (async), `app/scheduling/ticker.py::
process_schedule` (sync), and `app/ai/orchestrator.py::
_advance_mission_locked` (sync). Never a parallel execution path: every
Job a chain run creates goes through the exact same two pure functions
every other caller already uses.

Isolation: hooked into `execute_job()`'s outermost `finally` (like
Mission/Memory advancement, Phase 18/19) -- NOT inline like Phase 20's
hash, because advancing a chain run means *creating a new Job*, the same
"next-job-creation" concern Phase 18 already isolated from the current
job's own transaction. A bug in condition evaluation or Job creation here
can never flip the just-finished Job back to FAILED.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chains.conditions import evaluate_condition, technology_tags_for_nuclei
from app.db.sync_session import get_sync_session
from app.jobs.queue import get_queue
from app.jobs.service import prepare_job
from app.jobs.tasks import execute_job
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.models.mission_template import (
    ChainConditionType,
    ChainRun,
    ChainRunStatus,
    ChainRunStep,
    ChainRunStepStatus,
    MissionTemplate,
    MissionTemplateStep,
)
from app.targets.authorization import is_executable
from app.tools import registry

logger = logging.getLogger("cyberlab.chains")

_TERMINAL_CHAIN_RUN_STATUSES = (ChainRunStatus.COMPLETED, ChainRunStatus.FAILED, ChainRunStatus.CANCELLED)
_JOB_TERMINAL_STATUSES = (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED)


class ChainRunNotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stop_chain_run(session: Session, run: ChainRun, status: ChainRunStatus) -> ChainRun:
    run.status = status
    run.finished_at = _now()
    session.commit()
    return run


def _advance_chain_run_locked(session: Session, chain_run_id: uuid.UUID) -> ChainRun:
    """The testable, session-explicit core of advance_chain_run() -- takes
    an already-open sync Session so tests can drive two real, concurrent
    sessions against it directly, mirroring
    tests/ai/test_orchestrator.py::test_concurrent_advance_mission_creates_only_one_job.
    """
    # Blocking FOR UPDATE (not SKIP LOCKED) -- a concurrent second call
    # must wait, then re-read the now-current state and become a no-op,
    # never create a second Job for the same step. Same reasoning as
    # Phase 18's _advance_mission_locked.
    run = session.execute(select(ChainRun).where(ChainRun.id == chain_run_id).with_for_update()).scalar_one_or_none()
    if run is None:
        raise ChainRunNotFoundError(str(chain_run_id))

    if run.status in _TERMINAL_CHAIN_RUN_STATUSES:
        return run

    steps = list(
        session.execute(
            select(ChainRunStep).where(ChainRunStep.chain_run_id == run.id).order_by(ChainRunStep.step_order)
        ).scalars()
    )

    # Reconcile a QUEUED step against its Job's real outcome -- execute_job()
    # never writes to ChainRunStep itself, only this reconciliation does.
    queued_step = next((s for s in steps if s.status == ChainRunStepStatus.QUEUED), None)
    if queued_step is not None:
        job = session.get(Job, queued_step.job_id)
        if job is None or job.status not in _JOB_TERMINAL_STATUSES:
            return run  # still running (or the Job row vanished) -- check again later
        if job.status == JobStatus.SUCCESS:
            queued_step.status = ChainRunStepStatus.SUCCESS
        elif job.status == JobStatus.CANCELLED:
            queued_step.status = ChainRunStepStatus.CANCELLED
        else:
            queued_step.status = ChainRunStepStatus.FAILED
        session.commit()

    if any(s.status == ChainRunStepStatus.CANCELLED for s in steps):
        if run.status != ChainRunStatus.CANCELLED:
            return _stop_chain_run(session, run, ChainRunStatus.CANCELLED)
        return run

    # A step's Job actually failed -- a concerning, unexpected outcome,
    # stop-on-failure with no retry (same policy as Phase 18 Missions).
    if any(s.status == ChainRunStepStatus.FAILED for s in steps):
        if run.status != ChainRunStatus.FAILED:
            return _stop_chain_run(session, run, ChainRunStatus.FAILED)
        return run

    next_step = next((s for s in steps if s.status == ChainRunStepStatus.PENDING), None)
    if next_step is None:
        final_status = (
            ChainRunStatus.COMPLETED if any(s.status == ChainRunStepStatus.SUCCESS for s in steps) else ChainRunStatus.FAILED
        )
        return _stop_chain_run(session, run, final_status)

    previous_result: dict | None = None
    if next_step.step_order > 0:
        previous_step = steps[next_step.step_order - 1]
        previous_job = session.get(Job, previous_step.job_id) if previous_step.job_id else None
        previous_result = previous_job.result if previous_job is not None else None

        if not evaluate_condition(next_step.condition_type, next_step.condition_params, previous_result):
            # A condition legitimately not being met is a normal, expected
            # early stop of a conditional pipeline -- not a failure. This
            # is deliberately different from Phase 18's SKIPPED (always
            # authorization-revoked or a tool error, always concerning):
            # here, "port 80 wasn't open" is not an error, it's the correct
            # outcome of the branch not being taken.
            next_step.status = ChainRunStepStatus.SKIPPED
            next_step.skip_reason = f"condition not met: {next_step.condition_type.value}"
            return _stop_chain_run(session, run, ChainRunStatus.COMPLETED)

    # Re-verify authorization NOW, at execution time -- never trust the
    # authorization status the target had when the run was created.
    asset = session.get(Asset, run.target_id)
    if asset is None or not is_executable(asset):
        next_step.status = ChainRunStepStatus.SKIPPED
        next_step.skip_reason = (
            "asset no longer exists" if asset is None else f"asset authorization status is {asset.authorization_status.value}"
        )
        return _stop_chain_run(session, run, ChainRunStatus.FAILED)

    options = dict(next_step.options)
    # The one narrow, literal case the roadmap names explicitly ("nuclei,
    # filtre sur les tags pertinents") -- not a general templating
    # mechanism. Only applied when this step is nuclei, its own gating
    # condition was TECHNOLOGY_DETECTED, and it doesn't already specify
    # tags itself.
    if (
        next_step.tool == "nuclei"
        and next_step.condition_type == ChainConditionType.TECHNOLOGY_DETECTED
        and "tags" not in options
        and previous_result is not None
    ):
        tags = technology_tags_for_nuclei(previous_result)
        if tags:
            options["tags"] = tags

    try:
        prepared = prepare_job(next_step.tool, next_step.profile, options, asset.address)
    except (registry.ToolNotFoundError, registry.ToolValidationError) as exc:
        # SKIPPED, not FAILED: no Job exists to attach --
        # ck_chain_run_step_job_id_required_when_executed requires a
        # job_id for FAILED/SUCCESS/QUEUED.
        next_step.status = ChainRunStepStatus.SKIPPED
        next_step.skip_reason = str(exc)
        return _stop_chain_run(session, run, ChainRunStatus.FAILED)

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
    session.flush()

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

    next_step.job_id = job.id
    next_step.status = ChainRunStepStatus.QUEUED
    run.status = ChainRunStatus.RUNNING
    session.commit()
    return run


def advance_chain_run(chain_run_id: uuid.UUID) -> ChainRun:
    """Sync, self-opening -- the entry point used both by the API route
    (via asyncio.to_thread) and by execute_job()'s post-completion hook.
    """
    session = get_sync_session()
    try:
        return _advance_chain_run_locked(session, chain_run_id)
    finally:
        session.close()


def advance_chain_run_for_job(job_id: uuid.UUID | str) -> None:
    """Called by app/jobs/tasks.py::execute_job() strictly after that
    job's own session has already closed and its terminal status already
    committed. A Job that isn't part of any chain run is a cheap no-op --
    one indexed lookup on chain_run_steps.job_id, nothing else.
    """
    session = get_sync_session()
    try:
        step = session.execute(select(ChainRunStep).where(ChainRunStep.job_id == job_id)).scalar_one_or_none()
        if step is None:
            return
        chain_run_id = step.chain_run_id
    finally:
        session.close()

    advance_chain_run(chain_run_id)


def create_chain_run(template_id: uuid.UUID, target_id: uuid.UUID) -> ChainRun | None:
    """Sync, self-opening. Returns None if the template or target doesn't
    exist, or the template has no steps -- callers (the API route)
    translate that into a 404. Snapshots each MissionTemplateStep onto a
    new ChainRunStep at creation time -- never a live reference back to
    the (possibly later-edited) template, same precedent as Phase 18's
    MissionStep snapshotting the AI's plan. Starting a run is itself the
    human's deliberate action -- there is no separate approval step, so
    creation immediately triggers the first step via advance_chain_run().
    """
    session = get_sync_session()
    try:
        template = session.get(MissionTemplate, template_id)
        if template is None:
            return None
        asset = session.get(Asset, target_id)
        if asset is None:
            return None

        template_steps = list(
            session.execute(
                select(MissionTemplateStep)
                .where(MissionTemplateStep.template_id == template_id)
                .order_by(MissionTemplateStep.step_order)
            ).scalars()
        )
        if not template_steps:
            return None

        run = ChainRun(
            template_id=template_id, target_id=target_id, project_id=asset.project_id, status=ChainRunStatus.RUNNING
        )
        session.add(run)
        session.flush()

        for step in template_steps:
            session.add(
                ChainRunStep(
                    chain_run_id=run.id,
                    step_order=step.step_order,
                    tool=step.tool,
                    profile=step.profile,
                    options=dict(step.options),
                    condition_type=step.condition_type,
                    condition_params=dict(step.condition_params),
                    status=ChainRunStepStatus.PENDING,
                )
            )
        session.commit()
        run_id = run.id
    finally:
        session.close()

    return advance_chain_run(run_id)


def cancel_chain_run(chain_run_id: uuid.UUID) -> ChainRun:
    """Human kill switch. Never touches an in-flight Job -- that stays the
    job of the existing POST /api/jobs/{id}/cancel; cancelling a chain run
    only prevents any *future* step from ever being queued.
    """
    session = get_sync_session()
    try:
        run = session.execute(select(ChainRun).where(ChainRun.id == chain_run_id).with_for_update()).scalar_one_or_none()
        if run is None:
            raise ChainRunNotFoundError(str(chain_run_id))
        if run.status in _TERMINAL_CHAIN_RUN_STATUSES:
            return run  # no-op on an already-terminal run
        run.status = ChainRunStatus.CANCELLED
        run.finished_at = _now()
        session.commit()
        return run
    finally:
        session.close()
