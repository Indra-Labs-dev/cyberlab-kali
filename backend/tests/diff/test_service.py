import uuid
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.diff.service import find_previous_comparable_job, generate_change_events
from app.main import app
from app.models.asset_change_event import AssetChangeEvent, ChangeType
from app.models.job import Job, JobStatus


async def _make_authorized_asset() -> str:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Diff Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()
    return asset["id"]


def _make_job(session, asset_id: str, *, tool="nmap", profile=None, params=None, status=JobStatus.SUCCESS, result=None, offset_seconds=0) -> Job:
    job = Job(
        id=uuid.uuid4(),
        tool=tool,
        profile=profile,
        target="cyberlab-kali",
        target_id=uuid.UUID(asset_id),
        params=params or {"target": "cyberlab-kali"},
        status=status,
        result=result,
    )
    session.add(job)
    session.commit()
    # created_at has a server_default; nudge it directly so ordering between
    # baseline/current is deterministic regardless of real wall-clock timing.
    if offset_seconds:
        session.execute(
            Job.__table__.update()
            .where(Job.id == job.id)
            .values(created_at=datetime.now(timezone.utc) + timedelta(seconds=offset_seconds))
        )
        session.commit()
        session.refresh(job)
    return job


async def test_no_baseline_generates_no_events():
    asset_id = await _make_authorized_asset()
    session = get_sync_session()
    try:
        job = _make_job(session, asset_id, result={"hosts": [{"ports": [{"port": 80, "protocol": "tcp", "state": "open", "service": "http"}]}]})
        assert find_previous_comparable_job(session, job) is None
        events = generate_change_events(session, job)
        assert events == []
        session.commit()
    finally:
        session.close()


async def test_baseline_then_new_port_generates_event():
    asset_id = await _make_authorized_asset()
    session = get_sync_session()
    try:
        baseline = _make_job(
            session,
            asset_id,
            result={"hosts": [{"ports": [{"port": 80, "protocol": "tcp", "state": "open", "service": "http"}]}]},
            offset_seconds=-10,
        )
        current = _make_job(
            session,
            asset_id,
            result={
                "hosts": [
                    {
                        "ports": [
                            {"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
                            {"port": 8080, "protocol": "tcp", "state": "open", "service": "http-alt"},
                        ]
                    }
                ]
            },
        )
        found = find_previous_comparable_job(session, current)
        assert found is not None
        assert found.id == baseline.id

        events = generate_change_events(session, current)
        session.commit()
        assert len(events) == 1
        assert events[0].change_type == ChangeType.PORT_OPENED
        assert events[0].asset_id == uuid.UUID(asset_id)
        assert events[0].previous_job_id == baseline.id
        assert events[0].job_id == current.id

        persisted = session.query(AssetChangeEvent).filter_by(job_id=current.id).all()
        assert len(persisted) == 1
    finally:
        session.close()


async def test_different_profile_is_not_comparable():
    asset_id = await _make_authorized_asset()
    session = get_sync_session()
    try:
        _make_job(session, asset_id, profile="quick_scan", result={"hosts": []}, offset_seconds=-10)
        current = _make_job(session, asset_id, profile="full_scan", result={"hosts": []})
        assert find_previous_comparable_job(session, current) is None
    finally:
        session.close()


async def test_different_params_is_not_comparable():
    asset_id = await _make_authorized_asset()
    session = get_sync_session()
    try:
        _make_job(session, asset_id, params={"target": "cyberlab-kali", "ports": "80"}, result={"hosts": []}, offset_seconds=-10)
        current = _make_job(session, asset_id, params={"target": "cyberlab-kali", "ports": "443"}, result={"hosts": []})
        assert find_previous_comparable_job(session, current) is None


    finally:
        session.close()


async def test_different_tool_is_not_comparable():
    asset_id = await _make_authorized_asset()
    session = get_sync_session()
    try:
        _make_job(session, asset_id, tool="nmap", result={"hosts": []}, offset_seconds=-10)
        current = _make_job(session, asset_id, tool="whatweb", result={"results": []})
        assert find_previous_comparable_job(session, current) is None
    finally:
        session.close()


async def test_failed_baseline_is_not_used():
    asset_id = await _make_authorized_asset()
    session = get_sync_session()
    try:
        _make_job(session, asset_id, status=JobStatus.FAILED, result=None, offset_seconds=-10)
        current = _make_job(session, asset_id, result={"hosts": []})
        assert find_previous_comparable_job(session, current) is None
    finally:
        session.close()


async def test_no_changes_generates_no_events():
    asset_id = await _make_authorized_asset()
    session = get_sync_session()
    try:
        same_result = {"hosts": [{"ports": [{"port": 80, "protocol": "tcp", "state": "open", "service": "http"}]}]}
        _make_job(session, asset_id, result=same_result, offset_seconds=-10)
        current = _make_job(session, asset_id, result=same_result)
        events = generate_change_events(session, current)
        session.commit()
        assert events == []
    finally:
        session.close()


async def test_unsupported_tool_generates_no_events():
    asset_id = await _make_authorized_asset()
    session = get_sync_session()
    try:
        _make_job(session, asset_id, tool="nikto", result={"findings": ["a"]}, offset_seconds=-10)
        current = _make_job(session, asset_id, tool="nikto", result={"findings": ["a", "b"]})
        events = generate_change_events(session, current)
        session.commit()
        assert events == []
    finally:
        session.close()
