"""Post-Phase-23 consolidation (D.2) -- app/jobs/reconciliation.py's
Mission/ChainRun sweeps. Real Postgres throughout; get_queue() is mocked
for the detection/repair/no-false-positive/idempotence tests (same
convention as tests/ai/test_orchestrator.py and tests/chains/test_service.py
-- those properties don't depend on Redis), but the two "crash
reproduction" tests below deliberately do NOT mock it: they need a real RQ
job to land in the real, shared Redis instance to prove the exact failure
mode D.2 targets actually happens, not just that the detector's logic is
internally consistent. Cross-database safety (the real worker container
looks up job_id against the dev DB, never the test DB, so a stray real
pickup is a harmless no-op) is the same precedent tests/jobs/
test_reconciliation.py::test_reconcile_leaves_job_alone_when_rq_entry_still_exists
already relies on.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.orchestrator import MissionOrchestrator, _advance_mission_locked, approve_mission, cancel_mission
from app.ai.provider import AIProvider
from app.chains.service import _advance_chain_run_locked, cancel_chain_run, create_chain_run
from app.db.session import async_session_factory
from app.db.sync_session import get_sync_session
from app.jobs.reconciliation import reconcile_stuck_chain_runs, reconcile_stuck_missions
from app.main import app
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.models.mission import Mission, MissionStatus, MissionStep, MissionStepStatus
from app.models.mission_template import (
    ChainConditionType,
    ChainRun,
    ChainRunStatus,
    ChainRunStep,
    ChainRunStepStatus,
    MissionTemplate,
    MissionTemplateStep,
)


class FakeProvider(AIProvider):
    def __init__(self, response: str) -> None:
        self.response = response

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        return self.response


TWO_STEP_PLAN = (
    '{"steps": ['
    '{"label": "Port scan", "tool": "nmap", "target": "cyberlab-kali", "options": {}, "rationale": "recon"}, '
    '{"label": "Fingerprint", "tool": "whatweb", "target": "cyberlab-kali", "options": {}, "rationale": "id tech"}'
    "]}"
)


async def _make_authorized_asset() -> tuple[str, str]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Orchestration Reconciliation Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()
        assert asset["authorization_status"] == "LAB"
    return project["id"], asset["id"]


async def _create_mission(asset_id: str) -> str:
    orchestrator = MissionOrchestrator(FakeProvider(TWO_STEP_PLAN))
    async with async_session_factory() as db:
        asset = await db.get(Asset, uuid.UUID(asset_id))
        mission = await orchestrator.create_mission(db, target=asset, goal="recon", max_steps=10)
        return str(mission.id)


def _get_mission(mission_id: str) -> Mission:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return session.get(Mission, mission_id)
    finally:
        session.close()


def _get_mission_steps(mission_id: str) -> list[MissionStep]:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return list(
            session.execute(
                select(MissionStep).where(MissionStep.mission_id == mission_id).order_by(MissionStep.step_order)
            ).scalars()
        )
    finally:
        session.close()


def _set_step_status(step_id: uuid.UUID, status: MissionStepStatus | ChainRunStepStatus) -> None:
    session = get_sync_session()
    try:
        model = MissionStep if isinstance(status, MissionStepStatus) else ChainRunStep
        step = session.get(model, step_id)
        step.status = status
        session.commit()
    finally:
        session.close()


def _set_job_finished(job_id: uuid.UUID, *, status: JobStatus = JobStatus.SUCCESS, finished_at: datetime) -> None:
    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        job.status = status
        job.finished_at = finished_at
        session.commit()
    finally:
        session.close()


def _make_template() -> str:
    session = get_sync_session()
    try:
        template = MissionTemplate(id=uuid.uuid4(), name="Reconciliation Test Template")
        session.add(template)
        session.flush()
        for i, tool in enumerate(["nmap", "whatweb"]):
            session.add(
                MissionTemplateStep(
                    id=uuid.uuid4(),
                    template_id=template.id,
                    step_order=i,
                    tool=tool,
                    profile=None,
                    options={},
                    condition_type=ChainConditionType.ALWAYS,
                    condition_params={},
                )
            )
        session.commit()
        return str(template.id)
    finally:
        session.close()


def _get_run(run_id: str) -> ChainRun:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return session.get(ChainRun, run_id)
    finally:
        session.close()


def _get_run_steps(run_id: str) -> list[ChainRunStep]:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return list(
            session.execute(
                select(ChainRunStep).where(ChainRunStep.chain_run_id == run_id).order_by(ChainRunStep.step_order)
            ).scalars()
        )
    finally:
        session.close()


class _SimulatedCommitFailure(Exception):
    pass


def _fail_nth_commit(session: Session, n: int) -> None:
    """Patches THIS session instance's own commit method (never the Session
    class) so only its Nth call fails, reproducing "the transaction's
    commit failed for real" -- everything up to that point (flush, the real
    queue.enqueue() call) is genuine; only the commit outcome is
    deliberately injected. Every other call on this session, before or
    after, behaves exactly as normal.
    """
    original_commit = session.commit
    state = {"calls": 0}

    def _commit():
        state["calls"] += 1
        if state["calls"] == n:
            session.rollback()
            raise _SimulatedCommitFailure(f"commit #{n} deliberately failed")
        original_commit()

    session.commit = _commit


# --------------------------------------------------------------------------
# Reproduction: prove the exact D.2 failure shape actually happens
# --------------------------------------------------------------------------


async def test_advance_mission_crash_between_enqueue_and_second_commit_leaves_recoverable_state():
    """_advance_mission_locked() commits twice: once to resolve the just-
    finished step, once to queue the next one. This forces the SECOND
    commit to fail, after a real queue.enqueue() has already landed a real
    job in real Redis, and proves: the previous step's resolution survives
    (its own commit already succeeded), the next step is left PENDING
    rather than QUEUED-with-no-Job, mission.status is untouched, and no Job
    row exists for the step that was about to be created -- exactly the
    signature reconcile_stuck_missions() is built to find.
    """
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)  # step 0 -> QUEUED, mission -> RUNNING
    steps = _get_mission_steps(mission_id)
    # Simulate execute_job() finishing step 0's Job for real -- deliberately
    # NOT touching MissionStep here: only _advance_mission_locked() itself
    # is allowed to resolve QUEUED -> SUCCESS, as its own first commit below.
    _set_job_finished(steps[0].job_id, finished_at=datetime.now(timezone.utc))

    session = get_sync_session()
    try:
        _fail_nth_commit(session, n=2)  # 1st commit: resolve step0. 2nd (patched): would queue step1.
        with pytest.raises(_SimulatedCommitFailure):
            _advance_mission_locked(session, uuid.UUID(mission_id))
    finally:
        session.rollback()
        session.close()

    mission = _get_mission(mission_id)
    assert mission.status == MissionStatus.RUNNING  # never advanced past this, never corrupted either
    steps = _get_mission_steps(mission_id)
    assert steps[0].status == MissionStepStatus.SUCCESS  # survived: its own commit already succeeded
    assert steps[1].status == MissionStepStatus.PENDING  # never queued
    assert steps[1].job_id is None

    session = get_sync_session()
    try:
        jobs = list(session.execute(select(Job).where(Job.target_id == uuid.UUID(asset_id))).scalars())
        assert len(jobs) == 1  # only step 0's job -- step 1's flush()ed Job row was rolled back
    finally:
        session.close()

    # Cleanup: this test deliberately leaves the mission in the exact
    # "stuck" shape reconcile_stuck_missions() looks for -- cancel it so it
    # doesn't become a candidate for (and inflate the enqueue count of) a
    # later, unrelated test's own reconciliation sweep, which scans every
    # live Mission in the test database, not just the one it created.
    cancel_mission(mission_id)


async def test_advance_chain_run_crash_between_enqueue_and_second_commit_leaves_recoverable_state():
    """ChainRun analog of the Mission reproduction above -- same two-commit
    shape in _advance_chain_run_locked()."""
    _, asset_id = await _make_authorized_asset()
    template_id = _make_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
    run_id = str(run.id)
    steps = _get_run_steps(run_id)
    _set_job_finished(steps[0].job_id, finished_at=datetime.now(timezone.utc))

    session = get_sync_session()
    try:
        _fail_nth_commit(session, n=2)
        with pytest.raises(_SimulatedCommitFailure):
            _advance_chain_run_locked(session, uuid.UUID(run_id))
    finally:
        session.rollback()
        session.close()

    run = _get_run(run_id)
    assert run.status == ChainRunStatus.RUNNING
    steps = _get_run_steps(run_id)
    assert steps[0].status == ChainRunStepStatus.SUCCESS
    assert steps[1].status == ChainRunStepStatus.PENDING
    assert steps[1].job_id is None

    session = get_sync_session()
    try:
        jobs = list(session.execute(select(Job).where(Job.target_id == uuid.UUID(asset_id))).scalars())
        assert len(jobs) == 1
    finally:
        session.close()

    # See the equivalent Mission cleanup comment above.
    cancel_chain_run(uuid.UUID(run_id))


# --------------------------------------------------------------------------
# Detection + conservative repair
# --------------------------------------------------------------------------


async def test_reconcile_detects_and_repairs_stuck_mission():
    """Assertions are scoped to THIS mission's own steps/nudged-membership,
    never a global call count: reconcile_stuck_missions() is deliberately
    global in scope (same convention as reconcile_stuck_jobs()), so the
    shared test database may legitimately contain other live Missions left
    behind by other tests/runs -- this test must hold regardless of what
    else the same sweep also, correctly, touches.
    """
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
    steps = _get_mission_steps(mission_id)
    _set_job_finished(steps[0].job_id, finished_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)
    # steps[1] is left PENDING -- exactly the stuck shape, built directly
    # rather than by re-triggering the crash (proven separately above).

    session = get_sync_session()
    try:
        with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
            nudged = reconcile_stuck_missions(session, stuck_after=timedelta(minutes=5))
    finally:
        session.close()

    assert uuid.UUID(mission_id) in nudged
    steps = _get_mission_steps(mission_id)
    assert steps[1].status == MissionStepStatus.QUEUED
    assert steps[1].job_id is not None

    cancel_mission(mission_id)


async def test_reconcile_detects_and_repairs_stuck_chain_run():
    _, asset_id = await _make_authorized_asset()
    template_id = _make_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
    run_id = str(run.id)
    steps = _get_run_steps(run_id)
    _set_job_finished(steps[0].job_id, finished_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    _set_step_status(steps[0].id, ChainRunStepStatus.SUCCESS)

    session = get_sync_session()
    try:
        with patch("app.chains.service.get_queue", return_value=MagicMock()):
            nudged = reconcile_stuck_chain_runs(session, stuck_after=timedelta(minutes=5))
    finally:
        session.close()

    assert uuid.UUID(run_id) in nudged
    steps = _get_run_steps(run_id)
    assert steps[1].status == ChainRunStepStatus.QUEUED
    assert steps[1].job_id is not None

    cancel_chain_run(uuid.UUID(run_id))


async def test_reconcile_mission_all_steps_terminal_but_not_finalized():
    """Edge case with the same root cause: both steps already terminal, but
    mission.status was never flipped to COMPLETED/FAILED because that
    commit itself is what failed. advance_mission() must still correctly
    finalize it -- no special-cased repair logic needed for this shape."""
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
    steps = _get_mission_steps(mission_id)
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    _set_job_finished(steps[0].job_id, finished_at=old)
    _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)

    # Manually create step 1's terminal Job+status too (as if it had run),
    # without ever letting advance_mission's own finalizing commit happen.
    session = get_sync_session()
    try:
        job1 = Job(tool="whatweb", target="cyberlab-kali", project_id=None, target_id=uuid.UUID(asset_id), params={}, status=JobStatus.SUCCESS)
        job1.finished_at = old
        session.add(job1)
        session.flush()
        step1 = session.get(MissionStep, steps[1].id)
        step1.job_id = job1.id
        step1.status = MissionStepStatus.SUCCESS
        session.commit()
    finally:
        session.close()

    session = get_sync_session()
    try:
        with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
            nudged = reconcile_stuck_missions(session, stuck_after=timedelta(minutes=5))
    finally:
        session.close()

    assert uuid.UUID(mission_id) in nudged
    mission = _get_mission(mission_id)
    assert mission.status == MissionStatus.COMPLETED
    assert mission.finished_at is not None


# --------------------------------------------------------------------------
# No false positives on normal execution
#
# Like the detection tests above, assertions here are scoped to THIS
# mission/run's own artifacts, not a global "nothing was nudged" claim --
# the shared test database may legitimately contain other live Missions.
# --------------------------------------------------------------------------


async def test_reconcile_never_touches_mission_with_genuinely_in_flight_step():
    """A step legitimately still executing (Job status RUNNING, no
    finished_at) must never be touched, no matter how old approved_at is --
    this is the single most important guard against a false positive."""
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
    steps = _get_mission_steps(mission_id)

    session = get_sync_session()
    try:
        job = session.get(Job, steps[0].job_id)
        job.status = JobStatus.RUNNING  # genuinely in flight, no finished_at
        mission = session.get(Mission, uuid.UUID(mission_id))
        mission.approved_at = datetime.now(timezone.utc) - timedelta(hours=2)  # old, must not matter
        session.commit()
    finally:
        session.close()

    session = get_sync_session()
    try:
        with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
            nudged = reconcile_stuck_missions(session, stuck_after=timedelta(minutes=5))
    finally:
        session.close()

    assert uuid.UUID(mission_id) not in nudged
    steps = _get_mission_steps(mission_id)
    assert steps[0].status == MissionStepStatus.QUEUED  # untouched
    assert steps[1].status == MissionStepStatus.PENDING  # never queued a second time


async def test_reconcile_never_touches_chain_run_with_genuinely_in_flight_step():
    _, asset_id = await _make_authorized_asset()
    template_id = _make_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
    run_id = str(run.id)
    steps = _get_run_steps(run_id)

    session = get_sync_session()
    try:
        job = session.get(Job, steps[0].job_id)
        job.status = JobStatus.RUNNING
        run_row = session.get(ChainRun, uuid.UUID(run_id))
        run_row.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.commit()
    finally:
        session.close()

    session = get_sync_session()
    try:
        with patch("app.chains.service.get_queue", return_value=MagicMock()):
            nudged = reconcile_stuck_chain_runs(session, stuck_after=timedelta(minutes=5))
    finally:
        session.close()

    assert uuid.UUID(run_id) not in nudged
    steps = _get_run_steps(run_id)
    assert steps[0].status == ChainRunStepStatus.QUEUED
    assert steps[1].status == ChainRunStepStatus.PENDING


async def test_reconcile_leaves_recently_stalled_mission_alone():
    """A step resolved moments ago, next step still PENDING -- the same
    shape as "stuck", but within the grace window: this is the brief,
    entirely normal in-process gap between _advance_mission_locked()'s two
    commits (or the hook simply not having run yet), not a real failure."""
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
    steps = _get_mission_steps(mission_id)
    _set_job_finished(steps[0].job_id, finished_at=datetime.now(timezone.utc))  # just now
    _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)

    session = get_sync_session()
    try:
        with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
            nudged = reconcile_stuck_missions(session, stuck_after=timedelta(minutes=5))
    finally:
        session.close()

    assert uuid.UUID(mission_id) not in nudged
    steps = _get_mission_steps(mission_id)
    assert steps[1].status == MissionStepStatus.PENDING  # untouched, will be picked up on a later sweep

    cancel_mission(mission_id)


# --------------------------------------------------------------------------
# Idempotence: a repaired mission/run must never be re-nudged
# --------------------------------------------------------------------------


async def test_reconcile_stuck_missions_is_idempotent():
    """Scoped to this mission's own step1.job_id, not a global call count
    (see the comment on the detection tests above): proves no *second* Job
    was created for step 1 specifically, regardless of what else the same
    two sweeps may have also, correctly, touched."""
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
    steps = _get_mission_steps(mission_id)
    _set_job_finished(steps[0].job_id, finished_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        session = get_sync_session()
        try:
            first = reconcile_stuck_missions(session, stuck_after=timedelta(minutes=5))
        finally:
            session.close()

        session = get_sync_session()
        try:
            second = reconcile_stuck_missions(session, stuck_after=timedelta(minutes=5))
        finally:
            session.close()

    assert uuid.UUID(mission_id) in first
    assert uuid.UUID(mission_id) not in second  # step1 is now QUEUED with a non-terminal Job -- genuinely in flight

    steps_after_first = _get_mission_steps(mission_id)
    step1_job_id_after_first = steps_after_first[1].job_id
    assert step1_job_id_after_first is not None
    steps_after_second = _get_mission_steps(mission_id)
    assert steps_after_second[1].job_id == step1_job_id_after_first  # never a second Job for step 1

    cancel_mission(mission_id)


async def test_reconcile_stuck_chain_runs_is_idempotent():
    _, asset_id = await _make_authorized_asset()
    template_id = _make_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
    run_id = str(run.id)
    steps = _get_run_steps(run_id)
    _set_job_finished(steps[0].job_id, finished_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    _set_step_status(steps[0].id, ChainRunStepStatus.SUCCESS)

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        session = get_sync_session()
        try:
            first = reconcile_stuck_chain_runs(session, stuck_after=timedelta(minutes=5))
        finally:
            session.close()

        session = get_sync_session()
        try:
            second = reconcile_stuck_chain_runs(session, stuck_after=timedelta(minutes=5))
        finally:
            session.close()

    assert uuid.UUID(run_id) in first
    assert uuid.UUID(run_id) not in second

    steps_after_first = _get_run_steps(run_id)
    step1_job_id_after_first = steps_after_first[1].job_id
    assert step1_job_id_after_first is not None
    steps_after_second = _get_run_steps(run_id)
    assert steps_after_second[1].job_id == step1_job_id_after_first

    cancel_chain_run(uuid.UUID(run_id))
