"""Phase 21 -- app/chains/service.py: creation, progression, condition
gating, security, and concurrency. Mirrors tests/ai/test_orchestrator.py's
style (Phase 18's closest analog) -- real Postgres sessions, get_queue()
mocked so nothing actually touches Redis, and a real two-thread
concurrency test for the blocking FOR UPDATE lock. Unlike Phase 19's
memory service, nothing here calls asyncio.run() (no AI involvement at
all), so these tests are plain `async def` like Phase 18's.
"""

import threading
import uuid
from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.chains.service import (
    ChainRunNotFoundError,
    _advance_chain_run_locked,
    advance_chain_run,
    advance_chain_run_for_job,
    cancel_chain_run,
    create_chain_run,
)
from app.db.sync_session import get_sync_session
from app.main import app
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


async def _make_authorized_asset(**overrides) -> tuple[str, str]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Chain Fixture"})).json()
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


def _make_template(steps: list[dict]) -> str:
    """Each dict: {tool, profile?, options?, condition_type?, condition_params?}."""
    session = get_sync_session()
    try:
        template = MissionTemplate(id=uuid.uuid4(), name="Test Template")
        session.add(template)
        session.flush()
        for i, step in enumerate(steps):
            session.add(
                MissionTemplateStep(
                    id=uuid.uuid4(),
                    template_id=template.id,
                    step_order=i,
                    tool=step["tool"],
                    profile=step.get("profile"),
                    options=step.get("options", {}),
                    condition_type=step.get("condition_type", ChainConditionType.ALWAYS),
                    condition_params=step.get("condition_params", {}),
                )
            )
        session.commit()
        return str(template.id)
    finally:
        session.close()


def _two_step_port_open_template() -> str:
    return _make_template(
        [
            {"tool": "nmap", "profile": "quick_scan"},
            {
                "tool": "whatweb",
                "profile": "basic_fingerprint",
                "condition_type": ChainConditionType.PORT_OPEN,
                "condition_params": {"ports": [80, 443]},
            },
        ]
    )


def _get_run(run_id: str) -> ChainRun | None:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return session.get(ChainRun, run_id)
    finally:
        session.close()


def _get_steps(run_id: str) -> list[ChainRunStep]:
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


def _set_job_result(job_id: uuid.UUID, result: dict, status: JobStatus = JobStatus.SUCCESS) -> None:
    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        job.result = result
        job.status = status
        session.commit()
    finally:
        session.close()


# --------------------------------------------------------------------------
# create_chain_run
# --------------------------------------------------------------------------


async def test_create_chain_run_starts_first_step_immediately():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))

    assert run is not None
    assert run.status == ChainRunStatus.RUNNING
    steps = _get_steps(str(run.id))
    assert len(steps) == 2
    assert steps[0].status == ChainRunStepStatus.QUEUED  # ALWAYS -- runs immediately, no approval step
    assert steps[0].job_id is not None
    assert steps[1].status == ChainRunStepStatus.PENDING


async def test_create_chain_run_unknown_template_returns_none():
    _, asset_id = await _make_authorized_asset()
    assert create_chain_run(uuid.uuid4(), uuid.UUID(asset_id)) is None


async def test_create_chain_run_unknown_target_returns_none():
    template_id = _two_step_port_open_template()
    assert create_chain_run(uuid.UUID(template_id), uuid.uuid4()) is None


async def test_create_chain_run_template_with_no_steps_returns_none():
    template_id = _make_template([])
    _, asset_id = await _make_authorized_asset()
    assert create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id)) is None


# --------------------------------------------------------------------------
# advance_chain_run -- progression, conditions
# --------------------------------------------------------------------------


async def test_condition_met_progresses_to_next_step():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {"hosts": [{"ports": [{"port": 80, "state": "open"}]}]})

        advanced = advance_chain_run(run.id)

    assert advanced.status == ChainRunStatus.RUNNING
    steps = _get_steps(str(run.id))
    assert steps[1].status == ChainRunStepStatus.QUEUED
    assert steps[1].job_id is not None


async def test_condition_not_met_skips_step_and_completes_run_not_fails():
    """A condition legitimately not being met is a normal, expected stop
    -- deliberately COMPLETED, not FAILED (unlike Phase 18's SKIPPED,
    which is always concerning)."""
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()) as mock_get_queue:
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {"hosts": [{"ports": [{"port": 22, "state": "open"}]}]})

        mock_get_queue.reset_mock()
        advanced = advance_chain_run(run.id)

        assert advanced.status == ChainRunStatus.COMPLETED
        mock_get_queue.return_value.enqueue.assert_not_called()

    steps = _get_steps(str(run.id))
    assert steps[1].status == ChainRunStepStatus.SKIPPED
    assert "condition not met" in steps[1].skip_reason


async def test_all_steps_succeed_completes_run():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {"hosts": [{"ports": [{"port": 80, "state": "open"}]}]})
        advance_chain_run(run.id)

        steps = _get_steps(str(run.id))
        _set_job_result(steps[1].job_id, {"results": []})
        final = advance_chain_run(run.id)

    assert final.status == ChainRunStatus.COMPLETED
    assert final.finished_at is not None


async def test_step_job_failure_stops_run_failed():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()) as mock_get_queue:
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {}, status=JobStatus.FAILED)

        mock_get_queue.reset_mock()
        advanced = advance_chain_run(run.id)

        assert advanced.status == ChainRunStatus.FAILED
        mock_get_queue.return_value.enqueue.assert_not_called()

    steps = _get_steps(str(run.id))
    assert steps[1].status == ChainRunStepStatus.PENDING  # never touched


async def test_authorization_revoked_skips_step_and_fails_run():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()) as mock_get_queue:
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {"hosts": [{"ports": [{"port": 80, "state": "open"}]}]})

        await _revoke_authorization(asset_id)
        mock_get_queue.reset_mock()

        advanced = advance_chain_run(run.id)

        assert advanced.status == ChainRunStatus.FAILED
        mock_get_queue.return_value.enqueue.assert_not_called()

    steps = _get_steps(str(run.id))
    assert steps[1].status == ChainRunStepStatus.SKIPPED
    assert "UNKNOWN" in steps[1].skip_reason


async def test_hallucinated_tool_is_skipped_and_fails_run_without_crashing():
    _, asset_id = await _make_authorized_asset()
    template_id = _make_template([{"tool": "metasploit"}])  # not a registered tool

    with patch("app.chains.service.get_queue", return_value=MagicMock()) as mock_get_queue:
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))

    assert run.status == ChainRunStatus.FAILED
    mock_get_queue.return_value.enqueue.assert_not_called()
    steps = _get_steps(str(run.id))
    assert steps[0].status == ChainRunStepStatus.SKIPPED
    assert steps[0].job_id is None


async def test_nuclei_tags_auto_populated_from_detected_technology():
    _, asset_id = await _make_authorized_asset()
    template_id = _make_template(
        [
            {"tool": "whatweb", "profile": "basic_fingerprint"},
            {
                "tool": "nuclei",
                "profile": "quick_scan",
                "condition_type": ChainConditionType.TECHNOLOGY_DETECTED,
            },
        ]
    )

    with patch("app.chains.service.get_queue", return_value=MagicMock()) as mock_get_queue:
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {"results": [{"plugins": {"Apache": {}}}]})

        mock_get_queue.reset_mock()
        advance_chain_run(run.id)

    assert mock_get_queue.return_value.enqueue.call_count == 1
    call_args = mock_get_queue.return_value.enqueue.call_args
    full_params = call_args.args[3]  # positional: execute_job, job_id, tool, full_params, timeout
    assert "apache" in full_params.get("tags", "")


async def test_advance_or_cancel_unknown_run_raises():
    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        try:
            advance_chain_run(uuid.uuid4())
            assert False, "expected ChainRunNotFoundError"
        except ChainRunNotFoundError:
            pass
    try:
        cancel_chain_run(uuid.uuid4())
        assert False, "expected ChainRunNotFoundError"
    except ChainRunNotFoundError:
        pass


# --------------------------------------------------------------------------
# cancel_chain_run
# --------------------------------------------------------------------------


async def test_cancel_prevents_future_steps():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()) as mock_get_queue:
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {"hosts": [{"ports": [{"port": 80, "state": "open"}]}]})

        cancelled = cancel_chain_run(run.id)
        assert cancelled.status == ChainRunStatus.CANCELLED

        mock_get_queue.reset_mock()
        after_advance = advance_chain_run(run.id)
        assert after_advance.status == ChainRunStatus.CANCELLED
        mock_get_queue.return_value.enqueue.assert_not_called()


async def test_cancel_does_not_touch_in_flight_job():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        job_id = steps[0].job_id
        cancel_chain_run(run.id)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.QUEUED  # untouched by the run cancel
    finally:
        session.close()


async def test_cancel_on_terminal_run_is_a_no_op():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {}, status=JobStatus.FAILED)
        advance_chain_run(run.id)  # -> FAILED

    result = cancel_chain_run(run.id)
    assert result.status == ChainRunStatus.FAILED  # not overwritten to CANCELLED


# --------------------------------------------------------------------------
# advance_chain_run_for_job -- the execute_job() hook entry point
# --------------------------------------------------------------------------


async def test_advance_chain_run_for_job_resolves_the_right_run():
    _, asset_id = await _make_authorized_asset()
    template_id = _two_step_port_open_template()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
        steps = _get_steps(str(run.id))
        _set_job_result(steps[0].job_id, {"hosts": [{"ports": [{"port": 443, "state": "open"}]}]})

        advance_chain_run_for_job(steps[0].job_id)

    steps = _get_steps(str(run.id))
    assert steps[1].status == ChainRunStepStatus.QUEUED


async def test_advance_chain_run_for_job_unrelated_job_is_a_no_op():
    # Must not raise -- a Job not tied to any chain run is the common case.
    advance_chain_run_for_job(uuid.uuid4())


# --------------------------------------------------------------------------
# Concurrency: blocking FOR UPDATE must serialize, never double-create a Job
# --------------------------------------------------------------------------


async def test_concurrent_advance_chain_run_creates_only_one_job():
    _, asset_id = await _make_authorized_asset()
    template_id = _make_template([{"tool": "nmap", "profile": "quick_scan"}])

    session = get_sync_session()
    try:
        run = ChainRun(id=uuid.uuid4(), template_id=uuid.UUID(template_id), target_id=uuid.UUID(asset_id), status=ChainRunStatus.RUNNING)
        session.add(run)
        session.flush()
        session.add(
            ChainRunStep(
                id=uuid.uuid4(), chain_run_id=run.id, step_order=0, tool="nmap", profile="quick_scan",
                options={}, condition_type=ChainConditionType.ALWAYS, condition_params={},
                status=ChainRunStepStatus.PENDING,
            )
        )
        session.commit()
        run_id = run.id
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
        s = get_sync_session()
        try:
            results.append(_advance_chain_run_locked(s, run_id))
        finally:
            s.close()

    with patch("app.chains.service.get_queue", return_value=mock_queue):
        t1 = threading.Thread(target=call_advance)
        t1.start()
        assert started.wait(timeout=5), "thread1 never reached enqueue -- lock not acquired?"

        t2_done = threading.Event()

        def run_t2():
            call_advance()
            t2_done.set()

        t2 = threading.Thread(target=run_t2)
        t2.start()
        assert not t2_done.wait(timeout=1), "thread2 proceeded before thread1 committed -- lock not held"

        proceed.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

    assert len(results) == 2
    assert mock_queue.enqueue.call_count == 1

    steps = _get_steps(str(run_id))
    assert steps[0].status == ChainRunStepStatus.QUEUED

    session = get_sync_session()
    try:
        jobs = list(session.execute(select(Job).where(Job.target_id == uuid.UUID(asset_id))).scalars())
        assert len(jobs) == 1
    finally:
        session.close()
