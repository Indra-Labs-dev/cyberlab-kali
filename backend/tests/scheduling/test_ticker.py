from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.sync_session import get_sync_session
from app.main import app
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.models.scheduled_job import MIN_INTERVAL_SECONDS, ScheduledJob, ScheduledJobStatus
from app.scheduling.ticker import MAX_CONSECUTIVE_FAILURES, claim_due_schedules, run_due_schedules


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
    # tick running right now, regardless of whatever else is due in the
    # (shared, not per-test-isolated) test database.
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
    """Two real, separate DB sessions racing to claim the same due row --
    FOR UPDATE SKIP LOCKED must give it to exactly one, never block/duplicate,
    the Postgres-native reservation the spec asks for instead of a Redis lock."""
    _, schedule_id = await _make_authorized_schedule()
    _force_due(schedule_id)

    now = datetime.now(timezone.utc)
    stmt = (
        select(ScheduledJob)
        .where(ScheduledJob.status == ScheduledJobStatus.ACTIVE, ScheduledJob.next_run_at <= now)
        .with_for_update(skip_locked=True)
    )

    session1 = get_sync_session()
    session2 = get_sync_session()
    try:
        claimed1 = list(session1.execute(stmt).scalars())
        assert len(claimed1) == 1
        claimed2 = list(session2.execute(stmt).scalars())  # row still locked by session1 (no commit yet)
        assert len(claimed2) == 0
    finally:
        session1.rollback()
        session1.close()
        session2.rollback()
        session2.close()


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
