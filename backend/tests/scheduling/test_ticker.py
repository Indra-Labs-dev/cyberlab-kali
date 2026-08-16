import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.sync_session import get_sync_session
from app.main import app
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.models.scheduled_job import MIN_INTERVAL_SECONDS, ScheduledJob, ScheduledJobStatus
from app.scheduling.ticker import MAX_CONSECUTIVE_FAILURES, claim_due_schedules, run_due_schedules


def _wipe_scheduled_jobs() -> None:
    session = get_sync_session()
    try:
        session.execute(delete(ScheduledJob))
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _isolate_scheduled_jobs_table():
    """Test-hygiene fix (post-audit, P3) -- not a change to ticker.py.

    claim_due_schedules() (app/scheduling/ticker.py) intentionally scans
    the *entire* scheduled_jobs table -- that is correct, real production
    behavior for a single-user local tool, and must not change here. The
    problem is purely environmental: the shared `cyberlab_test` database
    is never truncated between pytest invocations within a session (see
    docs/development.md), so ScheduledJob rows created by this file, by
    tests/scheduling/test_schedules_api.py, and by tests/test_auth_middleware.py
    accumulate indefinitely. Because claim_due_schedules() advances
    next_run_at by a fixed MIN_INTERVAL_SECONDS on every claim, old rows
    from earlier runs resynchronize into large "all due at once" waves
    that can exceed its _BATCH_SIZE=50 cap and starve a test's own
    freshly-created row out of that tick's batch -- root-caused via direct
    SQL against cyberlab_test during the read-only audit (206+ ACTIVE rows
    clustering into the same due-minute), see docs/security.md.

    Scoped to this file only: wipes scheduled_jobs before and after each
    test here, so every ticker test always claims exactly what it itself
    created, regardless of what earlier test files or earlier runs left
    behind. Safe to delete freely -- nothing else has a foreign key into
    scheduled_jobs.
    """
    _wipe_scheduled_jobs()
    yield
    _wipe_scheduled_jobs()


async def _make_authorized_schedule(**overrides) -> tuple[str, str]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Ticker Fixture"})).json()
        payload = {"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"}
        asset = (await ac.post(f"/api/projects/{project['id']}/assets", json=payload)).json()
        body = {"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS}
        body.update(overrides)
        schedule = (await ac.post(f"/api/assets/{asset['id']}/schedules", json=body)).json()
    return asset["id"], schedule["id"]


def _force_due(schedule_id: str) -> None:
    session = get_sync_session()
    try:
        schedule = session.get(ScheduledJob, schedule_id)
        schedule.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()


def _get_schedule(schedule_id: str) -> ScheduledJob:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return session.get(ScheduledJob, schedule_id)
    finally:
        session.close()


async def test_run_due_schedules_creates_a_job():
    asset_id, schedule_id = await _make_authorized_schedule()
    _force_due(schedule_id)

    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
        run_due_schedules()

    schedule = _get_schedule(schedule_id)
    assert schedule.last_job_id is not None
    assert schedule.last_run_at is not None
    assert schedule.consecutive_failures == 0

    session = get_sync_session()
    try:
        job = session.get(Job, schedule.last_job_id)
        assert str(job.target_id) == asset_id
        assert job.tool == "nmap"
        assert job.status == JobStatus.QUEUED
    finally:
        session.close()


async def test_run_due_schedules_advances_next_run_at():
    _, schedule_id = await _make_authorized_schedule(interval_seconds=MIN_INTERVAL_SECONDS)
    _force_due(schedule_id)
    before = datetime.now(timezone.utc)

    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
        run_due_schedules()

    schedule = _get_schedule(schedule_id)
    assert schedule.next_run_at > before + timedelta(seconds=MIN_INTERVAL_SECONDS - 5)


async def test_not_due_schedule_is_not_processed():
    # A schedule created far enough in the future is never picked up by a
    # tick running right now.
    _, schedule_id = await _make_authorized_schedule(interval_seconds=MIN_INTERVAL_SECONDS)
    session = get_sync_session()
    try:
        schedule = session.get(ScheduledJob, schedule_id)
        schedule.next_run_at = datetime.now(timezone.utc) + timedelta(hours=1)
        session.commit()
    finally:
        session.close()

    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
        run_due_schedules()

    schedule = _get_schedule(schedule_id)
    assert schedule.last_job_id is None
    assert schedule.last_run_at is None


async def test_claiming_twice_immediately_does_not_double_claim():
    """Idempotency guarantee: a schedule claimed once must not be claimed
    again until its next interval, even if the ticker runs again
    immediately (simulating a fast restart loop)."""
    _, schedule_id = await _make_authorized_schedule()
    _force_due(schedule_id)

    session = get_sync_session()
    try:
        first = claim_due_schedules(session)
        assert len(first) == 1
        second = claim_due_schedules(session)
        assert len(second) == 0
    finally:
        session.close()


async def test_concurrent_claim_skip_locked_prevents_double_claim():
    """Phase 23 -- rewritten to call the real production function
    (claim_due_schedules(), not a reimplementation of its query) from two
    real threads/sessions. If someone ever removed
    `.with_for_update(skip_locked=True)` from the real function, the old
    version of this test (a hand-copied query) would keep passing -- this
    one would not, since it exercises the actual code.

    Unlike the blocking `SELECT ... FOR UPDATE` pattern used for Mission/
    Chain advancement elsewhere in this suite, SKIP LOCKED is explicitly
    non-blocking by design (see claim_due_schedules()'s own docstring): a
    second caller racing for an already-locked row must never wait for it,
    it must simply not see it and return empty-handed. So the assertion
    here is the opposite shape from the Mission/Chain tests: thread2's call
    must complete immediately (not block) AND come back with zero claimed
    rows (not double-claim) while thread1's transaction is still open.
    """
    _, schedule_id = await _make_authorized_schedule()
    _force_due(schedule_id)

    started = threading.Event()
    proceed = threading.Event()
    results: dict[str, list] = {}

    def call_claim_thread1() -> None:
        session = get_sync_session()
        real_commit = session.commit

        def blocking_commit(*args, **kwargs):
            started.set()
            assert proceed.wait(timeout=5), "test held up thread1 too long"
            return real_commit(*args, **kwargs)

        session.commit = blocking_commit
        try:
            results["t1"] = claim_due_schedules(session)
        finally:
            session.close()

    t1 = threading.Thread(target=call_claim_thread1)
    t1.start()
    assert started.wait(timeout=5), "thread1 never reached commit -- lock not acquired?"

    # thread1's transaction is now open and uncommitted, still holding the
    # row's lock. A second, real session racing for the same due row here
    # must return immediately (SKIP LOCKED never blocks) with nothing
    # claimed (the only due row is locked by thread1).
    session2 = get_sync_session()
    try:
        results["t2"] = claim_due_schedules(session2)
    finally:
        session2.close()
    assert results["t2"] == [], "SKIP LOCKED must skip the locked row, not double-claim it"

    proceed.set()
    t1.join(timeout=5)

    assert len(results["t1"]) == 1
    assert str(results["t1"][0].id) == schedule_id


async def test_asset_deleted_disables_schedule_on_next_tick():
    asset_id, schedule_id = await _make_authorized_schedule()
    _force_due(schedule_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.delete(f"/api/assets/{asset_id}")

    # The delete route already disables it synchronously (Phase 14 cleanup).
    schedule = _get_schedule(schedule_id)
    assert schedule.status == ScheduledJobStatus.DISABLED
    assert schedule.asset_id is None

    # Re-running the ticker on an already-DISABLED schedule must be a safe
    # no-op: it stays untouched (not re-claimed, no job created for it).
    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
        run_due_schedules()
    schedule_after = _get_schedule(schedule_id)
    assert schedule_after.status == ScheduledJobStatus.DISABLED
    assert schedule_after.last_job_id is None


async def test_asset_becomes_unauthorized_refuses_run_but_stays_active():
    asset_id, schedule_id = await _make_authorized_schedule()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.patch(f"/api/assets/{asset_id}", json={"authorization_status": "UNKNOWN"})
        assert response.json()["authorization_status"] == "UNKNOWN"

    _force_due(schedule_id)
    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()) as mock_queue:
        run_due_schedules()
        mock_queue.assert_not_called()

    schedule = _get_schedule(schedule_id)
    assert schedule.status == ScheduledJobStatus.ACTIVE  # recoverable, not disabled
    assert schedule.consecutive_failures == 1
    assert "UNKNOWN" in schedule.last_error
    assert schedule.last_job_id is None


async def test_tool_no_longer_valid_is_refused_without_crashing_ticker():
    _, schedule_id = await _make_authorized_schedule()
    _force_due(schedule_id)

    from app.tools import registry

    with patch.object(registry, "get_tool", side_effect=registry.ToolNotFoundError("nmap was removed")):
        with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()) as mock_queue:
            processed = run_due_schedules()
            mock_queue.assert_not_called()
    assert processed == 1  # claimed and processed (as a refusal), not skipped

    schedule = _get_schedule(schedule_id)
    assert schedule.status == ScheduledJobStatus.ACTIVE
    assert schedule.consecutive_failures == 1
    assert "removed" in schedule.last_error


async def test_consecutive_failures_auto_pauses_after_threshold():
    asset_id, schedule_id = await _make_authorized_schedule()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.patch(f"/api/assets/{asset_id}", json={"authorization_status": "UNKNOWN"})

    for _ in range(MAX_CONSECUTIVE_FAILURES):
        _force_due(schedule_id)
        with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
            run_due_schedules()

    schedule = _get_schedule(schedule_id)
    assert schedule.consecutive_failures == MAX_CONSECUTIVE_FAILURES
    assert schedule.status == ScheduledJobStatus.PAUSED

    # A paused schedule is never claimed even if forced due again.
    _force_due(schedule_id)
    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
        processed = run_due_schedules()
    assert processed == 0


async def test_recovering_authorization_resets_failures_on_next_success():
    asset_id, schedule_id = await _make_authorized_schedule()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.patch(f"/api/assets/{asset_id}", json={"authorization_status": "UNKNOWN"})

    _force_due(schedule_id)
    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
        run_due_schedules()
    assert _get_schedule(schedule_id).consecutive_failures == 1

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.patch(f"/api/assets/{asset_id}", json={"authorization_status": "AUTHORIZED"})

    _force_due(schedule_id)
    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
        run_due_schedules()

    schedule = _get_schedule(schedule_id)
    assert schedule.consecutive_failures == 0
    assert schedule.last_job_id is not None


async def test_bad_schedule_does_not_block_others_in_the_same_tick():
    asset_id, bad_schedule_id = await _make_authorized_schedule()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.patch(f"/api/assets/{asset_id}", json={"authorization_status": "UNKNOWN"})
    _, good_schedule_id = await _make_authorized_schedule()

    _force_due(bad_schedule_id)
    _force_due(good_schedule_id)

    with patch("app.scheduling.ticker.get_queue", return_value=MagicMock()):
        run_due_schedules()

    assert _get_schedule(good_schedule_id).last_job_id is not None
    assert _get_schedule(bad_schedule_id).last_job_id is None
    assert _get_schedule(bad_schedule_id).consecutive_failures == 1
