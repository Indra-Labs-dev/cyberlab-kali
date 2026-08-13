"""Phase 18 -- MissionOrchestrator lifecycle, security, and concurrency
tests. Mirrors tests/scheduling/test_ticker.py's style: real Postgres
sessions (sync for advance/approve/cancel, async for create), get_queue()
mocked so nothing actually touches Redis, and a real two-thread concurrency
test for the blocking FOR UPDATE lock (contrast with ticker.py's SKIP
LOCKED, which only needs two sessions, not two threads, since it never
blocks).
"""

import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.ai.orchestrator import (
    InvalidMissionStateError,
    MissionNotFoundError,
    MissionOrchestrator,
    _advance_mission_locked,
    advance_mission,
    approve_mission,
    cancel_mission,
)
from app.ai.provider import AIProvider
from app.db.session import async_session_factory
from app.db.sync_session import get_sync_session
from app.main import app
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.models.mission import Mission, MissionStatus, MissionStep, MissionStepStatus


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


async def _make_authorized_asset(**overrides) -> tuple[str, str]:
    """Returns (project_id, asset_id) for an asset whose hostname matches
    the lab-container pattern -- infer_default_authorization gives it LAB,
    an EXECUTABLE_STATUSES member, with no extra PATCH call needed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Mission Fixture"})).json()
        payload = {"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"}
        payload.update(overrides)
        asset = (await ac.post(f"/api/projects/{project['id']}/assets", json=payload)).json()
        assert asset["authorization_status"] == "LAB"
    return project["id"], asset["id"]


async def _revoke_authorization(asset_id: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.patch(f"/api/assets/{asset_id}", json={"authorization_status": "UNKNOWN"})
        assert response.json()["authorization_status"] == "UNKNOWN"


async def _create_mission(asset_id: str, goal: str = "recon the box", max_steps: int = 10, plan: str = TWO_STEP_PLAN) -> str:
    orchestrator = MissionOrchestrator(FakeProvider(plan))
    async with async_session_factory() as db:
        asset = await db.get(Asset, uuid.UUID(asset_id))
        mission = await orchestrator.create_mission(db, target=asset, goal=goal, max_steps=max_steps)
        return str(mission.id)


def _get_mission(mission_id: str) -> Mission:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return session.get(Mission, mission_id)
    finally:
        session.close()


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


def _set_step_status(step_id: uuid.UUID, status: MissionStepStatus) -> None:
    session = get_sync_session()
    try:
        step = session.get(MissionStep, step_id)
        step.status = status
        session.commit()
    finally:
        session.close()


# --------------------------------------------------------------------------
# create_mission
# --------------------------------------------------------------------------


async def test_create_mission_is_draft_and_never_auto_starts():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    mission = _get_mission(mission_id)
    assert mission.status == MissionStatus.DRAFT
    assert mission.approved_at is None
    steps = _get_steps(mission_id)
    assert len(steps) == 2
    assert all(s.status == MissionStepStatus.PENDING for s in steps)
    assert all(s.job_id is None for s in steps)


async def test_create_mission_target_id_is_server_side_not_model_chosen():
    _, asset_id = await _make_authorized_asset()
    # The fake plan's steps carry "target": "cyberlab-kali" as free text, and
    # never mention target_id at all -- create_mission must still stamp the
    # real, caller-supplied Asset id onto the Mission, never something
    # parsed from the model's own output.
    mission_id = await _create_mission(asset_id)
    mission = _get_mission(mission_id)
    assert str(mission.target_id) == asset_id


async def test_create_mission_truncates_to_max_steps():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id, max_steps=1)
    steps = _get_steps(mission_id)
    assert len(steps) == 1
    assert steps[0].step_order == 0


async def test_create_mission_permits_unauthorized_target_as_draft():
    # Mirrors POST /api/ai/plan: proposing/creating a DRAFT is never
    # blocked by authorization -- only advance_mission()'s is_executable()
    # check is the hard gate.
    project = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Unauth Mission Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "external", "hostname": "example.com", "type": "DOMAIN"},
            )
        ).json()
        assert asset["authorization_status"] == "UNKNOWN"

    mission_id = await _create_mission(asset["id"], plan=TWO_STEP_PLAN.replace("cyberlab-kali", "example.com"))
    mission = _get_mission(mission_id)
    assert mission.status == MissionStatus.DRAFT


# --------------------------------------------------------------------------
# approve_mission / advance_mission progression
# --------------------------------------------------------------------------


async def test_approve_mission_queues_first_step_and_creates_a_job():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        mission = approve_mission(mission_id)

    assert mission.status == MissionStatus.RUNNING
    assert mission.approved_at is not None
    steps = _get_steps(mission_id)
    assert steps[0].status == MissionStepStatus.QUEUED
    assert steps[0].job_id is not None
    assert steps[1].status == MissionStepStatus.PENDING

    session = get_sync_session()
    try:
        job = session.get(Job, steps[0].job_id)
        assert job.tool == "nmap"
        assert str(job.target_id) == asset_id
        assert job.status == JobStatus.QUEUED
    finally:
        session.close()


async def test_approve_mission_rejects_non_draft():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)  # DRAFT -> RUNNING
        with pytest.raises(InvalidMissionStateError):
            approve_mission(mission_id)  # no longer DRAFT


async def test_advance_mission_progresses_to_next_step_after_success():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
        steps = _get_steps(mission_id)
        _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)  # simulate execute_job finishing

        mission = advance_mission(mission_id)

    assert mission.status == MissionStatus.RUNNING
    steps = _get_steps(mission_id)
    assert steps[1].status == MissionStepStatus.QUEUED
    assert steps[1].job_id is not None


async def test_mission_completes_when_all_steps_succeed():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
        steps = _get_steps(mission_id)
        _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)
        advance_mission(mission_id)
        steps = _get_steps(mission_id)
        _set_step_status(steps[1].id, MissionStepStatus.SUCCESS)
        mission = advance_mission(mission_id)

    assert mission.status == MissionStatus.COMPLETED
    assert mission.finished_at is not None


async def test_mission_stops_on_step_failure_no_retry():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()) as mock_get_queue:
        approve_mission(mission_id)
        steps = _get_steps(mission_id)
        _set_step_status(steps[0].id, MissionStepStatus.FAILED)

        mission = advance_mission(mission_id)
        assert mission.status == MissionStatus.FAILED

        # Calling advance again must not somehow retry or advance further.
        mock_get_queue.reset_mock()
        mission_again = advance_mission(mission_id)
        assert mission_again.status == MissionStatus.FAILED
        mock_get_queue.return_value.enqueue.assert_not_called()

    steps = _get_steps(mission_id)
    assert steps[1].status == MissionStepStatus.PENDING  # never touched


# --------------------------------------------------------------------------
# Security: re-validation at every step, never a bypass
# --------------------------------------------------------------------------


async def test_authorization_revoked_between_steps_skips_and_stops_mission():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()) as mock_get_queue:
        approve_mission(mission_id)
        steps = _get_steps(mission_id)
        _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)

        await _revoke_authorization(asset_id)
        mock_get_queue.reset_mock()

        mission = advance_mission(mission_id)

        assert mission.status == MissionStatus.FAILED
        mock_get_queue.return_value.enqueue.assert_not_called()

    steps = _get_steps(mission_id)
    assert steps[1].status == MissionStepStatus.SKIPPED
    assert "UNKNOWN" in steps[1].skip_reason


async def test_max_steps_cap_is_enforced_even_with_extra_pending_rows():
    """Defense in depth: even if a MissionStep beyond max_steps existed
    (shouldn't happen via create_mission's own truncation, but
    advance_mission must not trust that alone), it is never executed."""
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id, max_steps=1)

    # Manually append a second PENDING step beyond the cap to simulate a
    # data-layer inconsistency and prove advance_mission still enforces it.
    session = get_sync_session()
    try:
        session.add(
            MissionStep(
                mission_id=uuid.UUID(mission_id),
                step_order=1,
                label="Should never run",
                tool="whatweb",
                profile=None,
                options={},
                rationale="",
                status=MissionStepStatus.PENDING,
            )
        )
        session.commit()
    finally:
        session.close()

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
        steps = _get_steps(mission_id)
        _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)
        mission = advance_mission(mission_id)

    assert mission.status == MissionStatus.COMPLETED
    steps = _get_steps(mission_id)
    assert steps[1].status == MissionStepStatus.PENDING  # capped, never queued


async def test_step_with_hallucinated_tool_is_skipped_without_crashing():
    _, asset_id = await _make_authorized_asset()
    plan = '{"steps": [{"label": "Exploit it", "tool": "metasploit", "target": "cyberlab-kali", "options": {}}]}'
    mission_id = await _create_mission(asset_id, plan=plan)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()) as mock_get_queue:
        mission = approve_mission(mission_id)

    assert mission.status == MissionStatus.FAILED
    mock_get_queue.return_value.enqueue.assert_not_called()
    steps = _get_steps(mission_id)
    # SKIPPED, not FAILED: no Job was ever created for this step, and the DB
    # check constraint requires a job_id for FAILED (see mission.py).
    assert steps[0].status == MissionStepStatus.SKIPPED
    assert steps[0].job_id is None


# --------------------------------------------------------------------------
# cancel_mission -- kill switch
# --------------------------------------------------------------------------


async def test_cancel_mission_prevents_future_steps():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()) as mock_get_queue:
        approve_mission(mission_id)
        steps = _get_steps(mission_id)
        _set_step_status(steps[0].id, MissionStepStatus.SUCCESS)

        mission = cancel_mission(mission_id)
        assert mission.status == MissionStatus.CANCELLED

        mock_get_queue.reset_mock()
        mission_after_advance = advance_mission(mission_id)
        assert mission_after_advance.status == MissionStatus.CANCELLED
        mock_get_queue.return_value.enqueue.assert_not_called()


async def test_cancel_mission_does_not_touch_in_flight_job():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
        steps = _get_steps(mission_id)
        job_id = steps[0].job_id

        cancel_mission(mission_id)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.QUEUED  # untouched by the Mission cancel
    finally:
        session.close()


async def test_cancel_mission_on_terminal_mission_is_a_no_op():
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id)

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        approve_mission(mission_id)
        steps = _get_steps(mission_id)
        _set_step_status(steps[0].id, MissionStepStatus.FAILED)
        advance_mission(mission_id)  # -> FAILED

    mission = cancel_mission(mission_id)
    assert mission.status == MissionStatus.FAILED  # not overwritten to CANCELLED


async def test_advance_or_approve_unknown_mission_raises():
    fake_id = uuid.uuid4()
    with pytest.raises(MissionNotFoundError):
        advance_mission(fake_id)
    with pytest.raises(MissionNotFoundError):
        cancel_mission(fake_id)
    with pytest.raises(MissionNotFoundError):
        approve_mission(fake_id)


# --------------------------------------------------------------------------
# Concurrency: blocking FOR UPDATE must serialize, never double-create a Job
# --------------------------------------------------------------------------


async def test_concurrent_advance_mission_creates_only_one_job():
    """Two real threads, each with their own sync Session, both calling
    _advance_mission_locked() for the same RUNNING mission. The first to
    acquire the row lock must finish (create the Job, commit) before the
    second's own `SELECT ... FOR UPDATE` can even return -- proven here by
    blocking the first thread's enqueue() call on an Event until the test
    has confirmed the second thread is still stuck waiting on the lock.
    """
    _, asset_id = await _make_authorized_asset()
    mission_id = await _create_mission(asset_id, max_steps=1)

    # DRAFT -> APPROVED only (no advance yet) so the mission has exactly one
    # PENDING step when the two threads race.
    session = get_sync_session()
    try:
        mission = session.get(Mission, uuid.UUID(mission_id))
        mission.status = MissionStatus.APPROVED
        session.commit()
    finally:
        session.close()

    started = threading.Event()
    proceed = threading.Event()

    def blocking_enqueue(*args, **kwargs):
        started.set()
        assert proceed.wait(timeout=5), "test held up thread1 too long"

    mock_queue = MagicMock()
    mock_queue.enqueue.side_effect = blocking_enqueue

    results: list = []

    def call_advance():
        session = get_sync_session()
        try:
            results.append(_advance_mission_locked(session, uuid.UUID(mission_id)))
        finally:
            session.close()

    with patch("app.ai.orchestrator.get_queue", return_value=mock_queue):
        t1 = threading.Thread(target=call_advance)
        t1.start()
        assert started.wait(timeout=5), "thread1 never reached enqueue -- lock not acquired?"

        t2_done = threading.Event()

        def run_t2():
            call_advance()
            t2_done.set()

        t2 = threading.Thread(target=run_t2)
        t2.start()
        # thread2's SELECT ... FOR UPDATE must still be blocked on Postgres's
        # row lock, held by thread1's still-open (uncommitted) transaction.
        assert not t2_done.wait(timeout=1), "thread2 proceeded before thread1 committed -- lock not held"

        proceed.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

    assert len(results) == 2
    assert mock_queue.enqueue.call_count == 1

    steps = _get_steps(mission_id)
    non_pending = [s for s in steps if s.status != MissionStepStatus.PENDING]
    assert len(non_pending) == 1
    assert non_pending[0].status == MissionStepStatus.QUEUED

    session = get_sync_session()
    try:
        jobs = list(session.execute(select(Job).where(Job.target_id == uuid.UUID(asset_id))).scalars())
        assert len(jobs) == 1
    finally:
        session.close()
