import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_project_and_target(client, **target_overrides):
    project = (await client.post("/api/projects", json={"name": "Fixture Project"})).json()
    payload = {"name": "Fixture Target", "hostname": "10.0.0.5", "target_type": "IP"}
    payload.update(target_overrides)
    target = (await client.post(f"/api/projects/{project['id']}/targets", json=payload)).json()
    return project, target


async def test_get_target(client):
    _, target = await _make_project_and_target(client)
    response = await client.get(f"/api/targets/{target['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == target["id"]


async def test_get_nonexistent_target_404(client):
    response = await client.get("/api/targets/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_update_target_authorization_status(client):
    _, target = await _make_project_and_target(client)
    response = await client.patch(f"/api/targets/{target['id']}", json={"authorization_status": "AUTHORIZED"})
    assert response.status_code == 200
    assert response.json()["authorization_status"] == "AUTHORIZED"


async def test_update_target_cannot_remove_all_addresses(client):
    _, target = await _make_project_and_target(client)
    response = await client.patch(f"/api/targets/{target['id']}", json={"hostname": None})
    assert response.status_code == 422


async def test_delete_target(client):
    _, target = await _make_project_and_target(client)
    response = await client.delete(f"/api/targets/{target['id']}")
    assert response.status_code == 204
    assert (await client.get(f"/api/targets/{target['id']}")).status_code == 404


async def test_list_targets_filters_by_project(client):
    project_a, target_a = await _make_project_and_target(client, name="A")
    project_b = (await client.post("/api/projects", json={"name": "Project B"})).json()
    await client.post(
        f"/api/projects/{project_b['id']}/targets",
        json={"name": "B", "hostname": "10.0.0.6", "target_type": "IP"},
    )

    response = await client.get(f"/api/targets?project_id={project_a['id']}")
    assert response.status_code == 200
    ids = [t["id"] for t in response.json()]
    assert target_a["id"] in ids
    assert all(t["project_id"] == project_a["id"] for t in response.json())


async def test_list_targets_filters_by_authorization_status(client):
    await _make_project_and_target(client, name="lab-one", hostname="cyberlab-lab-x-1")
    response = await client.get("/api/targets?authorization_status=LAB")
    assert response.status_code == 200
    assert all(t["authorization_status"] == "LAB" for t in response.json())
