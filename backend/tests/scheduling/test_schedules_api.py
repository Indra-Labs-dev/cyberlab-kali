import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.scheduled_job import MIN_INTERVAL_SECONDS


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_authorized_asset(client, **overrides):
    """cyberlab-kali auto-infers to LAB authorization (see
    app/targets/authorization.py) -- executable without a manual PATCH."""
    project = (await client.post("/api/projects", json={"name": "Schedule Fixture Project"})).json()
    payload = {"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"}
    payload.update(overrides)
    asset = (await client.post(f"/api/projects/{project['id']}/assets", json=payload)).json()
    return project, asset


async def _make_unauthorized_asset(client, **overrides):
    project = (await client.post("/api/projects", json={"name": "Unauthorized Fixture Project"})).json()
    payload = {"name": "external", "hostname": "scanme.example.org", "type": "HOST"}
    payload.update(overrides)
    asset = (await client.post(f"/api/projects/{project['id']}/assets", json=payload)).json()
    assert asset["authorization_status"] == "UNKNOWN"
    return project, asset


async def test_create_schedule(client):
    _, asset = await _make_authorized_asset(client)
    response = await client.post(
        f"/api/assets/{asset['id']}/schedules",
        json={"tool": "nmap", "profile": "quick_scan", "interval_seconds": MIN_INTERVAL_SECONDS},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["asset_id"] == asset["id"]
    assert body["project_id"] == asset["project_id"]
    assert body["consecutive_failures"] == 0
    assert body["next_run_at"] is not None


async def test_create_schedule_rejects_interval_below_minimum(client):
    _, asset = await _make_authorized_asset(client)
    response = await client.post(
        f"/api/assets/{asset['id']}/schedules",
        json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS - 1},
    )
    assert response.status_code == 422


async def test_create_schedule_rejects_unknown_tool(client):
    _, asset = await _make_authorized_asset(client)
    response = await client.post(
        f"/api/assets/{asset['id']}/schedules",
        json={"tool": "not-a-real-tool", "interval_seconds": MIN_INTERVAL_SECONDS},
    )
    assert response.status_code == 404


async def test_create_schedule_rejects_invalid_profile(client):
    _, asset = await _make_authorized_asset(client)
    response = await client.post(
        f"/api/assets/{asset['id']}/schedules",
        json={"tool": "nmap", "profile": "not-a-real-profile", "interval_seconds": MIN_INTERVAL_SECONDS},
    )
    assert response.status_code == 400


async def test_create_schedule_rejects_unauthorized_asset(client):
    _, asset = await _make_unauthorized_asset(client)
    response = await client.post(
        f"/api/assets/{asset['id']}/schedules",
        json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS},
    )
    assert response.status_code == 403


async def test_create_schedule_404_for_nonexistent_asset(client):
    response = await client.post(
        "/api/assets/00000000-0000-0000-0000-000000000000/schedules",
        json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS},
    )
    assert response.status_code == 404


async def test_list_asset_schedules(client):
    _, asset = await _make_authorized_asset(client)
    await client.post(
        f"/api/assets/{asset['id']}/schedules", json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS}
    )
    response = await client.get(f"/api/assets/{asset['id']}/schedules")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_get_schedule(client):
    _, asset = await _make_authorized_asset(client)
    created = (
        await client.post(f"/api/assets/{asset['id']}/schedules", json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS})
    ).json()
    response = await client.get(f"/api/schedules/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_pause_and_resume_schedule(client):
    _, asset = await _make_authorized_asset(client)
    created = (
        await client.post(f"/api/assets/{asset['id']}/schedules", json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS})
    ).json()

    paused = (await client.patch(f"/api/schedules/{created['id']}", json={"status": "PAUSED"})).json()
    assert paused["status"] == "PAUSED"

    resumed = (await client.patch(f"/api/schedules/{created['id']}", json={"status": "ACTIVE"})).json()
    assert resumed["status"] == "ACTIVE"
    assert resumed["consecutive_failures"] == 0


async def test_update_schedule_interval(client):
    _, asset = await _make_authorized_asset(client)
    created = (
        await client.post(f"/api/assets/{asset['id']}/schedules", json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS})
    ).json()
    updated = (
        await client.patch(f"/api/schedules/{created['id']}", json={"interval_seconds": MIN_INTERVAL_SECONDS * 2})
    ).json()
    assert updated["interval_seconds"] == MIN_INTERVAL_SECONDS * 2


async def test_delete_schedule(client):
    _, asset = await _make_authorized_asset(client)
    created = (
        await client.post(f"/api/assets/{asset['id']}/schedules", json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS})
    ).json()
    response = await client.delete(f"/api/schedules/{created['id']}")
    assert response.status_code == 204
    assert (await client.get(f"/api/schedules/{created['id']}")).status_code == 404


async def test_run_schedule_now(client, monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setattr("app.api.routes.schedules.get_queue", lambda: MagicMock())

    _, asset = await _make_authorized_asset(client)
    created = (
        await client.post(
            f"/api/assets/{asset['id']}/schedules",
            json={"tool": "nmap", "options": {"ports": "9000"}, "interval_seconds": MIN_INTERVAL_SECONDS},
        )
    ).json()

    response = await client.post(f"/api/schedules/{created['id']}/run")
    assert response.status_code == 200
    body = response.json()
    assert body["last_job_id"] is not None
    assert body["last_run_at"] is not None

    job = (await client.get(f"/api/jobs/{body['last_job_id']}")).json()
    assert job["target_id"] == asset["id"]
    assert job["tool"] == "nmap"


async def test_run_schedule_now_rejects_disabled(client):
    _, asset = await _make_authorized_asset(client)
    created = (
        await client.post(f"/api/assets/{asset['id']}/schedules", json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS})
    ).json()
    await client.patch(f"/api/schedules/{created['id']}", json={"status": "DISABLED"})
    response = await client.post(f"/api/schedules/{created['id']}/run")
    assert response.status_code == 400


async def test_deleting_asset_disables_its_schedules(client):
    _, asset = await _make_authorized_asset(client)
    created = (
        await client.post(f"/api/assets/{asset['id']}/schedules", json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS})
    ).json()

    response = await client.delete(f"/api/assets/{asset['id']}")
    assert response.status_code == 204

    schedule = (await client.get(f"/api/schedules/{created['id']}")).json()
    assert schedule["status"] == "DISABLED"
    assert schedule["asset_id"] is None  # ON DELETE SET NULL


async def test_deleting_target_disables_its_schedules_too(client):
    """Target IS Asset (Phase 13, same table) -- deleting via the legacy
    /api/targets path must trigger the same schedule cleanup."""
    _, asset = await _make_authorized_asset(client)
    created = (
        await client.post(f"/api/assets/{asset['id']}/schedules", json={"tool": "nmap", "interval_seconds": MIN_INTERVAL_SECONDS})
    ).json()

    response = await client.delete(f"/api/targets/{asset['id']}")
    assert response.status_code == 204

    schedule = (await client.get(f"/api/schedules/{created['id']}")).json()
    assert schedule["status"] == "DISABLED"


async def test_list_asset_changes_empty(client):
    _, asset = await _make_authorized_asset(client)
    response = await client.get(f"/api/assets/{asset['id']}/changes")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_asset_changes_404_for_nonexistent_asset(client):
    response = await client.get("/api/assets/00000000-0000-0000-0000-000000000000/changes")
    assert response.status_code == 404
