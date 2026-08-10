from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_create_job_rejects_unknown_tool(client):
    response = await client.post("/api/jobs", json={"tool": "metasploit", "target": "10.0.0.1"})
    assert response.status_code == 404


async def test_create_job_rejects_flag_injection_target(client):
    response = await client.post("/api/jobs", json={"tool": "nmap", "target": "--script=vuln"})
    assert response.status_code == 400


async def test_create_job_rejects_invalid_option(client):
    response = await client.post(
        "/api/jobs",
        json={"tool": "nmap", "target": "10.0.0.1", "options": {"ports": "80;whoami"}},
    )
    assert response.status_code == 400


@patch("app.api.routes.jobs.get_queue")
async def test_create_job_valid_enqueues_and_persists(mock_get_queue, client):
    mock_queue = MagicMock()
    mock_get_queue.return_value = mock_queue

    response = await client.post(
        "/api/jobs",
        json={"tool": "nmap", "target": "10.0.0.1", "options": {"ports": "80"}},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tool"] == "nmap"
    assert body["target"] == "10.0.0.1"
    assert body["status"] == "QUEUED"
    assert body["params"] == {"ports": "80", "target": "10.0.0.1"}
    mock_queue.enqueue.assert_called_once()

    job_id = body["id"]
    get_response = await client.get(f"/api/jobs/{job_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == job_id


async def test_get_nonexistent_job_returns_404(client):
    response = await client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_cancel_nonexistent_job_returns_404(client):
    response = await client.post("/api/jobs/00000000-0000-0000-0000-000000000000/cancel")
    assert response.status_code == 404


async def test_create_job_requires_target_or_target_id(client):
    response = await client.post("/api/jobs", json={"tool": "nmap"})
    assert response.status_code == 422


async def test_create_job_with_nonexistent_target_id_404(client):
    response = await client.post(
        "/api/jobs", json={"tool": "nmap", "target_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert response.status_code == 404


async def test_create_job_rejects_unauthorized_unknown_target(client):
    project = (await client.post("/api/projects", json={"name": "Authz Test Project"})).json()
    target = (
        await client.post(
            f"/api/projects/{project['id']}/targets",
            json={"name": "scanme", "hostname": "scanme.nmap.org", "target_type": "DOMAIN"},
        )
    ).json()
    assert target["authorization_status"] == "UNKNOWN"

    response = await client.post("/api/jobs", json={"tool": "nmap", "target_id": target["id"]})
    assert response.status_code == 403


@patch("app.api.routes.jobs.get_queue")
async def test_create_job_with_authorized_target_id_succeeds_and_links_project(mock_get_queue, client):
    mock_get_queue.return_value = MagicMock()

    project = (await client.post("/api/projects", json={"name": "Authorized Project"})).json()
    target = (
        await client.post(
            f"/api/projects/{project['id']}/targets",
            json={"name": "kali", "hostname": "cyberlab-kali", "target_type": "CONTAINER"},
        )
    ).json()
    assert target["authorization_status"] == "LAB"

    response = await client.post(
        "/api/jobs", json={"tool": "nmap", "target_id": target["id"], "options": {"ports": "9000"}}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["target"] == "cyberlab-kali"
    assert body["project_id"] == project["id"]
    assert body["target_id"] == target["id"]
