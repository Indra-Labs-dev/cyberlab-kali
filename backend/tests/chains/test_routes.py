"""Phase 21 -- /api/chains/templates and /api/chains/runs routes.
Black-box, real API calls only (mirrors tests/ai/test_mission_routes.py's
style), get_queue() mocked so job creation never touches real Redis.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_authorized_asset(client: AsyncClient) -> str:
    project = (await client.post("/api/projects", json={"name": "Chain Route Fixture"})).json()
    asset = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"},
        )
    ).json()
    assert asset["authorization_status"] == "LAB"
    return asset["id"]


_TWO_STEP_TEMPLATE_BODY = {
    "name": "nmap then whatweb",
    "description": "quick recon chain",
    "steps": [
        {"tool": "nmap", "profile": "quick_scan"},
        {
            "tool": "whatweb",
            "profile": "basic_fingerprint",
            "condition_type": "PORT_OPEN",
            "condition_params": {"ports": [80, 443]},
        },
    ],
}


# --------------------------------------------------------------------------
# MissionTemplate CRUD
# --------------------------------------------------------------------------


async def test_create_template(client):
    response = await client.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "nmap then whatweb"
    assert len(body["steps"]) == 2
    assert body["steps"][0]["condition_type"] == "ALWAYS"
    assert body["steps"][1]["condition_type"] == "PORT_OPEN"


async def test_create_template_rejects_unregistered_tool(client):
    response = await client.post(
        "/api/chains/templates",
        json={"name": "bad", "steps": [{"tool": "metasploit"}]},
    )
    assert response.status_code == 422


async def test_create_template_rejects_invalid_profile(client):
    response = await client.post(
        "/api/chains/templates",
        json={"name": "bad", "steps": [{"tool": "nmap", "profile": "not_a_real_profile"}]},
    )
    assert response.status_code == 422


async def test_create_template_rejects_first_step_with_non_always_condition(client):
    response = await client.post(
        "/api/chains/templates",
        json={"name": "bad", "steps": [{"tool": "nmap", "condition_type": "PORT_OPEN", "condition_params": {"ports": [80]}}]},
    )
    assert response.status_code == 422


async def test_create_template_rejects_empty_steps(client):
    response = await client.post("/api/chains/templates", json={"name": "empty", "steps": []})
    assert response.status_code == 422


async def test_list_and_get_template(client):
    created = (await client.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)).json()

    listed = await client.get("/api/chains/templates")
    assert listed.status_code == 200
    assert any(t["id"] == created["id"] for t in listed.json())

    fetched = await client.get(f"/api/chains/templates/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


async def test_get_unknown_template_404(client):
    response = await client.get(f"/api/chains/templates/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_delete_template(client):
    created = (await client.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)).json()
    response = await client.delete(f"/api/chains/templates/{created['id']}")
    assert response.status_code == 204
    assert (await client.get(f"/api/chains/templates/{created['id']}")).status_code == 404


async def test_delete_unknown_template_404(client):
    response = await client.delete(f"/api/chains/templates/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_delete_template_preserves_run_history(client):
    asset_id = await _make_authorized_asset(client)
    template = (await client.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)).json()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = (
            await client.post("/api/chains/runs", json={"template_id": template["id"], "target_id": asset_id})
        ).json()

    await client.delete(f"/api/chains/templates/{template['id']}")

    fetched_run = await client.get(f"/api/chains/runs/{run['id']}")
    assert fetched_run.status_code == 200
    assert fetched_run.json()["template_id"] is None  # SET NULL, run itself intact
    assert len(fetched_run.json()["steps"]) == 2  # steps were snapshotted, not lost


# --------------------------------------------------------------------------
# ChainRun lifecycle
# --------------------------------------------------------------------------


async def test_create_run_starts_immediately_no_approval_step(client):
    asset_id = await _make_authorized_asset(client)
    template = (await client.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)).json()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        response = await client.post("/api/chains/runs", json={"template_id": template["id"], "target_id": asset_id})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["steps"][0]["status"] == "QUEUED"
    assert body["steps"][0]["job_id"] is not None
    assert body["steps"][1]["status"] == "PENDING"


async def test_create_run_unknown_template_404(client):
    asset_id = await _make_authorized_asset(client)
    response = await client.post("/api/chains/runs", json={"template_id": str(uuid.uuid4()), "target_id": asset_id})
    assert response.status_code == 404


async def test_create_run_unknown_target_404(client):
    template = (await client.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)).json()
    response = await client.post("/api/chains/runs", json={"template_id": template["id"], "target_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_list_runs_filters_by_target_id(client):
    asset_id = await _make_authorized_asset(client)
    other_asset_id = await _make_authorized_asset(client)
    template = (await client.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)).json()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        await client.post("/api/chains/runs", json={"template_id": template["id"], "target_id": asset_id})
        await client.post("/api/chains/runs", json={"template_id": template["id"], "target_id": other_asset_id})

    response = await client.get("/api/chains/runs", params={"target_id": asset_id})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["target_id"] == asset_id


async def test_get_unknown_run_404(client):
    response = await client.get(f"/api/chains/runs/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_cancel_run(client):
    asset_id = await _make_authorized_asset(client)
    template = (await client.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)).json()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = (await client.post("/api/chains/runs", json={"template_id": template["id"], "target_id": asset_id})).json()
        response = await client.post(f"/api/chains/runs/{run['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


async def test_cancel_unknown_run_404(client):
    response = await client.post(f"/api/chains/runs/{uuid.uuid4()}/cancel")
    assert response.status_code == 404


async def test_run_against_unauthorized_target_skips_first_step_and_fails():
    """Security: a run must not silently bypass Target authorization --
    the first step (ALWAYS) is still gated by is_executable() just like
    every later step."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Unauth Chain Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "external", "hostname": "example.com", "type": "DOMAIN"},
            )
        ).json()
        assert asset["authorization_status"] == "UNKNOWN"

        template = (await ac.post("/api/chains/templates", json=_TWO_STEP_TEMPLATE_BODY)).json()

        with patch("app.chains.service.get_queue", return_value=MagicMock()) as mock_get_queue:
            response = await ac.post("/api/chains/runs", json={"template_id": template["id"], "target_id": asset["id"]})

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "FAILED"
        assert body["steps"][0]["status"] == "SKIPPED"
        mock_get_queue.return_value.enqueue.assert_not_called()
