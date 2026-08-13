"""Phase 18.5 -- proves execute_job() and the Mission lifecycle are wired
together correctly and safely:
1. A real Job finishing SUCCESS actually progresses its Mission (the
   reconciliation logic in app.ai.orchestrator._advance_mission_locked).
2. A failure in mission advancement can never retroactively change a Job
   that already finished SUCCESS -- the isolation guarantee described in
   app/jobs/tasks.py::execute_job's outer finally block.
"""

import uuid
from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.ai.orchestrator import MissionOrchestrator, approve_mission
from app.ai.provider import AIProvider
from app.db.session import async_session_factory
from app.db.sync_session import get_sync_session
from app.jobs.tasks import execute_job
from app.main import app
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.models.mission import MissionStep, MissionStepStatus

TWO_STEP_PLAN = (
    '{"steps": ['
    '{"label": "Port scan", "tool": "nmap", "target": "cyberlab-kali", "options": {}, "rationale": "recon"}, '
    '{"label": "Fingerprint", "tool": "whatweb", "target": "cyberlab-kali", "options": {}, "rationale": "id tech"}'
    "]}"
)


class FakeProvider(AIProvider):
    def __init__(self, response: str) -> None:
        self.response = response

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        return self.response


async def _make_authorized_asset() -> str:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Mission Integration Fixture"})).json()
        payload = {"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"}
        asset = (await ac.post(f"/api/projects/{project['id']}/assets", json=payload)).json()
        assert asset["authorization_status"] == "LAB"
    return asset["id"]


async def _create_and_approve_mission(asset_id: str) -> str:
    orchestrator = MissionOrchestrator(FakeProvider(TWO_STEP_PLAN))
    async with async_session_factory() as db:
        asset = await db.get(Asset, uuid.UUID(asset_id))
        mission = await orchestrator.create_mission(db, target=asset, goal="recon", max_steps=10)
        mission_id = str(mission.id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
    return mission_id


def _get_steps(mission_id: str) -> list[MissionStep]:
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


async def test_execute_job_success_progresses_mission_to_next_step():
    asset_id = await _make_authorized_asset()
    mission_id = await _create_and_approve_mission(asset_id)
    steps = _get_steps(mission_id)
    job_id = str(steps[0].job_id)
    assert steps[0].status == MissionStepStatus.QUEUED

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "", "stderr": "", "exit_code": 0}):
        execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.SUCCESS
    finally:
        session.close()

    # The post-completion hook (advance_mission_for_job, called from
    # execute_job's outermost finally) must have reconciled step 1 to
    # SUCCESS and queued step 2 -- with no explicit advance_mission() call
    # from this test, proving the wiring is automatic, not manual.
    steps = _get_steps(mission_id)
    assert steps[0].status == MissionStepStatus.SUCCESS
    assert steps[1].status == MissionStepStatus.QUEUED
    assert steps[1].job_id is not None


async def test_job_stays_success_even_if_mission_advancement_fails():
    asset_id = await _make_authorized_asset()
    mission_id = await _create_and_approve_mission(asset_id)
    steps = _get_steps(mission_id)
    job_id = str(steps[0].job_id)

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "", "stderr": "", "exit_code": 0}):
        with patch("app.ai.orchestrator.advance_mission_for_job", side_effect=RuntimeError("boom")):
            # execute_job() must not raise even though the mission-side hook
            # blew up -- it's swallowed (and logged) by execute_job's own
            # isolated try/except, never propagated to the RQ worker.
            execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        # The Job's own status/result, committed and closed *before* the
        # mission hook ever ran, must be completely unaffected.
        assert job.status == JobStatus.SUCCESS
        assert job.exit_code == 0
        assert job.finished_at is not None
    finally:
        session.close()

    # The step never got reconciled (the hook that would have done it
    # raised before touching the DB) -- still QUEUED, not silently marked
    # FAILED or SUCCESS by some fallback path.
    steps = _get_steps(mission_id)
    assert steps[0].status == MissionStepStatus.QUEUED
