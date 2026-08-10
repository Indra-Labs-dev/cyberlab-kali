import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_create_and_get_project(client):
    response = await client.post("/api/projects", json={"name": "Web Security Lab", "description": "test"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Web Security Lab"
    assert body["status"] == "ACTIVE"

    project_id = body["id"]
    get_response = await client.get(f"/api/projects/{project_id}")
    assert get_response.status_code == 200
    summary = get_response.json()
    assert summary["target_count"] == 0
    assert summary["job_count"] == 0
    assert summary["finding_count"] == 0
    assert summary["lab_count"] == 0


async def test_list_projects_includes_created(client):
    await client.post("/api/projects", json={"name": "Listable Project"})
    response = await client.get("/api/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert "Listable Project" in names


async def test_get_nonexistent_project_404(client):
    response = await client.get("/api/projects/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_update_project(client):
    create = await client.post("/api/projects", json={"name": "To Update"})
    project_id = create.json()["id"]

    response = await client.patch(f"/api/projects/{project_id}", json={"status": "ARCHIVED"})
    assert response.status_code == 200
    assert response.json()["status"] == "ARCHIVED"


async def test_delete_project(client):
    create = await client.post("/api/projects", json={"name": "To Delete"})
    project_id = create.json()["id"]

    response = await client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 204

    get_response = await client.get(f"/api/projects/{project_id}")
    assert get_response.status_code == 404


async def test_delete_project_with_targets_returns_409(client):
    create = await client.post("/api/projects", json={"name": "Has Targets"})
    project_id = create.json()["id"]
    await client.post(
        f"/api/projects/{project_id}/targets",
        json={"name": "t1", "hostname": "10.0.0.1", "target_type": "IP"},
    )

    response = await client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 409


async def test_create_target_under_project(client):
    create = await client.post("/api/projects", json={"name": "Target Owner"})
    project_id = create.json()["id"]

    response = await client.post(
        f"/api/projects/{project_id}/targets",
        json={"name": "Juice Shop", "url": "http://juice-shop:3000", "target_type": "LAB"},
    )
    assert response.status_code == 201
    target = response.json()
    assert target["project_id"] == project_id
    assert target["authorization_status"] == "UNKNOWN"  # not a recognized lab/local hostname


async def test_create_target_infers_lab_authorization_for_cyberlab_containers(client):
    create = await client.post("/api/projects", json={"name": "Lab Project"})
    project_id = create.json()["id"]

    response = await client.post(
        f"/api/projects/{project_id}/targets",
        json={"name": "DVWA", "hostname": "cyberlab-lab-dvwa-abcd1234", "target_type": "CONTAINER"},
    )
    assert response.status_code == 201
    assert response.json()["authorization_status"] == "LAB"


async def test_create_target_infers_local_authorization(client):
    create = await client.post("/api/projects", json={"name": "Local Project"})
    project_id = create.json()["id"]

    response = await client.post(
        f"/api/projects/{project_id}/targets",
        json={"name": "loopback", "hostname": "127.0.0.1", "target_type": "IP"},
    )
    assert response.status_code == 201
    assert response.json()["authorization_status"] == "LOCAL"


async def test_create_target_requires_at_least_one_address(client):
    create = await client.post("/api/projects", json={"name": "No Address"})
    project_id = create.json()["id"]

    response = await client.post(
        f"/api/projects/{project_id}/targets",
        json={"name": "nothing", "target_type": "OTHER"},
    )
    assert response.status_code == 422


async def test_create_target_under_nonexistent_project_404(client):
    response = await client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/targets",
        json={"name": "orphan", "hostname": "10.0.0.1", "target_type": "IP"},
    )
    assert response.status_code == 404
