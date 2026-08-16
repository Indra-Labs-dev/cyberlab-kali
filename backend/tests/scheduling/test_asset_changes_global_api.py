"""SOC-lite -- GET /api/asset-changes, the cross-project counterpart of
GET /api/assets/{asset_id}/changes (Phase 14). Mirrors tests/scheduling/
test_schedules_api.py's client fixture and tests/diff/test_service.py's
direct-session AssetChangeEvent creation (no route exists to create one,
same as the single-asset route's own tests never do either -- events are
only ever produced by the Diff Engine, ~app/diff/service.py).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.main import app
from app.models.asset_change_event import AssetChangeEvent, ChangeType
from app.models.finding import Severity
from app.models.job import Job, JobStatus


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_asset(client, project_name: str = "Global Changes Fixture") -> tuple[str, str]:
    project = (await client.post("/api/projects", json={"name": project_name})).json()
    asset = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
        )
    ).json()
    return project["id"], asset["id"]


def _make_change(
    asset_id: str,
    *,
    change_type: ChangeType = ChangeType.PORT_OPENED,
    severity: Severity = Severity.MEDIUM,
    detected_at: datetime | None = None,
) -> str:
    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool="nmap", target="cyberlab-kali", target_id=uuid.UUID(asset_id), params={}, status=JobStatus.SUCCESS)
        session.add(job)
        session.flush()

        event = AssetChangeEvent(
            asset_id=uuid.UUID(asset_id),
            job_id=job.id,
            previous_job_id=None,
            change_type=change_type,
            severity=severity,
            field="port:22",
            old_value=None,
            new_value="22/tcp open",
            change_metadata={},
        )
        session.add(event)
        session.commit()
        if detected_at is not None:
            session.execute(AssetChangeEvent.__table__.update().where(AssetChangeEvent.id == event.id).values(detected_at=detected_at))
            session.commit()
        session.refresh(event)
        return str(event.id)
    finally:
        session.close()


async def test_global_asset_changes_empty_for_a_fresh_project_with_no_changes(client):
    """Scoped via project_id, not a bare GET -- this is a genuinely global,
    unscoped endpoint, so the shared test database (reused across pytest
    invocations, see docs/development.md) may legitimately already contain
    events from other tests/sessions. A freshly created project can never
    have any, regardless of what else exists globally.
    """
    project_id, _ = await _make_asset(client)
    response = await client.get("/api/asset-changes", params={"project_id": project_id})
    assert response.status_code == 200
    assert response.json() == []


async def test_global_asset_changes_spans_multiple_projects_and_assets(client):
    _, asset_a = await _make_asset(client, "Project A")
    _, asset_b = await _make_asset(client, "Project B")
    change_a = _make_change(asset_a)
    change_b = _make_change(asset_b)

    response = await client.get("/api/asset-changes")
    assert response.status_code == 200
    ids = {c["id"] for c in response.json()}
    assert {change_a, change_b} <= ids


async def test_global_asset_changes_filters_by_project_id(client):
    project_a, asset_a = await _make_asset(client, "Project A")
    _, asset_b = await _make_asset(client, "Project B")
    change_a = _make_change(asset_a)
    change_b = _make_change(asset_b)

    response = await client.get("/api/asset-changes", params={"project_id": project_a})
    assert response.status_code == 200
    ids = {c["id"] for c in response.json()}
    assert change_a in ids
    assert change_b not in ids


async def test_global_asset_changes_unknown_project_id_returns_empty_list_not_404():
    """A filter on a list endpoint, same convention as GET /api/findings?
    project_id= -- an unmatched id is an empty result, never an error."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/asset-changes", params={"project_id": str(uuid.uuid4())})
    assert response.status_code == 200
    assert response.json() == []


async def test_global_asset_changes_filters_by_severity(client):
    _, asset_id = await _make_asset(client)
    high = _make_change(asset_id, severity=Severity.HIGH)
    low = _make_change(asset_id, severity=Severity.LOW)

    response = await client.get("/api/asset-changes", params={"severity": "HIGH"})
    assert response.status_code == 200
    ids = {c["id"] for c in response.json()}
    assert high in ids
    assert low not in ids


async def test_global_asset_changes_filters_by_change_type(client):
    _, asset_id = await _make_asset(client)
    opened = _make_change(asset_id, change_type=ChangeType.PORT_OPENED)
    closed = _make_change(asset_id, change_type=ChangeType.PORT_CLOSED)

    response = await client.get("/api/asset-changes", params={"change_type": "PORT_CLOSED"})
    assert response.status_code == 200
    ids = {c["id"] for c in response.json()}
    assert closed in ids
    assert opened not in ids


async def test_global_asset_changes_ordered_most_recent_first(client):
    _, asset_id = await _make_asset(client)
    now = datetime.now(timezone.utc)
    older = _make_change(asset_id, detected_at=now - timedelta(hours=2))
    newer = _make_change(asset_id, detected_at=now)

    response = await client.get("/api/asset-changes")
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert ids.index(newer) < ids.index(older)


async def test_global_asset_changes_respects_limit(client):
    _, asset_id = await _make_asset(client)
    for _ in range(5):
        _make_change(asset_id)

    response = await client.get("/api/asset-changes", params={"limit": 2})
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_global_asset_changes_before_cursor_paginates(client):
    _, asset_id = await _make_asset(client)
    now = datetime.now(timezone.utc)
    older = _make_change(asset_id, detected_at=now - timedelta(hours=2))
    newer = _make_change(asset_id, detected_at=now)

    response = await client.get("/api/asset-changes", params={"before": now.isoformat()})
    assert response.status_code == 200
    ids = {c["id"] for c in response.json()}
    assert older in ids
    assert newer not in ids
