"""Phase 18.7/18.10 -- POST /api/ai/missions and its approve/cancel/list/get
routes. Black-box, real API calls only (mirrors tests/ai/test_ai_security_boundary.py's
style), get_queue() mocked so job creation never touches real Redis.
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.provider import AIProvider
from app.api.routes.ai import get_provider
from app.main import app

TWO_STEP_PLAN = (
    '{"steps": ['
    '{"label": "Port scan", "tool": "nmap", "target": "cyberlab-kali", "options": {}, "rationale": "recon"}, '
    '{"label": "Fingerprint", "tool": "whatweb", "target": "cyberlab-kali", "options": {}, "rationale": "id tech"}'
    "]}"
)


class FakeProvider(AIProvider):
    def __init__(self, response: str = TWO_STEP_PLAN) -> None:
        self.response = response

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        return self.response


@pytest.fixture
async def client():
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_provider, None)


async def _make_authorized_asset(client: AsyncClient) -> str:
    project = (await client.post("/api/projects", json={"name": "Mission Route Fixture"})).json()
    payload = {"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"}
    asset = (await client.post(f"/api/projects/{project['id']}/assets", json=payload)).json()
    assert asset["authorization_status"] == "LAB"
    return asset["id"]


async def test_create_mission_returns_draft_with_steps(client):
    asset_id = await _make_authorized_asset(client)
    response = await client.post("/api/ai/missions", json={"target_id": asset_id, "goal": "recon the box"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["target_id"] == asset_id
    assert len(body["steps"]) == 2
    assert all(step["status"] == "PENDING" for step in body["steps"])


async def test_create_mission_requires_real_target_id(client):
    import uuid

    response = await client.post("/api/ai/missions", json={"target_id": str(uuid.uuid4()), "goal": "recon"})
    assert response.status_code == 404


async def test_create_mission_rejects_missing_target_id(client):
    response = await client.post("/api/ai/missions", json={"goal": "recon"})
    assert response.status_code == 422  # target_id is a required field, unlike JobCreateRequest's target


async def test_approve_mission_queues_first_step(client):
    asset_id = await _make_authorized_asset(client)
    mission = (await client.post("/api/ai/missions", json={"target_id": asset_id, "goal": "recon"})).json()

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        response = await client.post(f"/api/ai/missions/{mission['id']}/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["approved_at"] is not None
    assert body["steps"][0]["status"] == "QUEUED"
    assert body["steps"][0]["job_id"] is not None


async def test_approve_mission_twice_returns_400(client):
    asset_id = await _make_authorized_asset(client)
    mission = (await client.post("/api/ai/missions", json={"target_id": asset_id, "goal": "recon"})).json()

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        await client.post(f"/api/ai/missions/{mission['id']}/approve")
        second = await client.post(f"/api/ai/missions/{mission['id']}/approve")
    assert second.status_code == 400


async def test_approve_unknown_mission_returns_404(client):
    import uuid

    response = await client.post(f"/api/ai/missions/{uuid.uuid4()}/approve")
    assert response.status_code == 404


async def test_cancel_mission_prevents_further_progress(client):
    asset_id = await _make_authorized_asset(client)
    mission = (await client.post("/api/ai/missions", json={"target_id": asset_id, "goal": "recon"})).json()

    with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()):
        await client.post(f"/api/ai/missions/{mission['id']}/approve")
        response = await client.post(f"/api/ai/missions/{mission['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


async def test_list_missions_filters_by_target_id(client):
    asset_id = await _make_authorized_asset(client)
    other_asset_id = await _make_authorized_asset(client)
    await client.post("/api/ai/missions", json={"target_id": asset_id, "goal": "recon A"})
    await client.post("/api/ai/missions", json={"target_id": other_asset_id, "goal": "recon B"})

    response = await client.get("/api/ai/missions", params={"target_id": asset_id})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["target_id"] == asset_id


async def test_get_mission_by_id(client):
    asset_id = await _make_authorized_asset(client)
    created = (await client.post("/api/ai/missions", json={"target_id": asset_id, "goal": "recon"})).json()

    response = await client.get(f"/api/ai/missions/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_unknown_mission_returns_404(client):
    import uuid

    response = await client.get(f"/api/ai/missions/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_mission_cannot_run_against_unauthorized_target():
    """Security: creating a DRAFT is permitted against an unauthorized
    target (mirrors POST /api/ai/plan), but approving it must not create a
    Job -- the step is SKIPPED and the mission stops, never a silent bypass
    of is_executable()."""
    app.dependency_overrides[get_provider] = lambda: FakeProvider(
        TWO_STEP_PLAN.replace("cyberlab-kali", "example.com")
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            project = (await ac.post("/api/projects", json={"name": "Unauth Mission Route Fixture"})).json()
            asset = (
                await ac.post(
                    f"/api/projects/{project['id']}/assets",
                    json={"name": "external", "hostname": "example.com", "type": "DOMAIN"},
                )
            ).json()
            assert asset["authorization_status"] == "UNKNOWN"

            mission = (await ac.post("/api/ai/missions", json={"target_id": asset["id"], "goal": "recon"})).json()

            with patch("app.ai.orchestrator.get_queue", return_value=MagicMock()) as mock_get_queue:
                response = await ac.post(f"/api/ai/missions/{mission['id']}/approve")

            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "FAILED"
            assert body["steps"][0]["status"] == "SKIPPED"
            mock_get_queue.return_value.enqueue.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_provider, None)
