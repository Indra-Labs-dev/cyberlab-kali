"""Phase 19 -- GET/POST /api/ai/projects/{id}/summary(/regenerate) and
POST /api/ai/chat with project_id. Black-box HTTP tests, real Postgres
sessions for fixture setup (mirrors tests/ai/test_mission_routes.py).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.provider import AIProvider
from app.api.routes.ai import get_provider
from app.db.sync_session import get_sync_session
from app.main import app
from app.models.asset_change_event import AssetChangeEvent, ChangeType
from app.models.finding import Severity
from app.models.job import Job, JobStatus


class FakeProvider(AIProvider):
    def __init__(self, response: str = "Everything looks fine.") -> None:
        self.response = response
        self.last_system: str | None = None

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_system = system
        return self.response


@pytest.fixture
async def client():
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_provider, None)


async def _make_project_with_asset(client: AsyncClient) -> tuple[str, str]:
    project = (await client.post("/api/projects", json={"name": "Memory Route Fixture"})).json()
    asset = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"},
        )
    ).json()
    return project["id"], asset["id"]


def _add_change_event(asset_id: str) -> None:
    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool="nmap", target="cyberlab-kali", params={}, status=JobStatus.SUCCESS)
        session.add(job)
        session.flush()
        session.add(
            AssetChangeEvent(
                id=uuid.uuid4(), asset_id=uuid.UUID(asset_id), job_id=job.id,
                change_type=ChangeType.PORT_OPENED, severity=Severity.MEDIUM,
                field="port:8080/tcp", old_value=None, new_value="open",
            )
        )
        session.commit()
    finally:
        session.close()


async def test_get_summary_404_when_never_generated(client):
    project_id, _ = await _make_project_with_asset(client)
    response = await client.get(f"/api/ai/projects/{project_id}/summary")
    assert response.status_code == 404


async def test_get_summary_404_for_unknown_project(client):
    response = await client.get(f"/api/ai/projects/{uuid.uuid4()}/summary")
    assert response.status_code == 404


async def test_regenerate_creates_and_get_then_returns_it(client):
    project_id, _ = await _make_project_with_asset(client)

    regen = await client.post(f"/api/ai/projects/{project_id}/summary/regenerate")
    assert regen.status_code == 200
    assert regen.json()["summary"] == "Everything looks fine."
    assert regen.json()["project_id"] == project_id

    fetched = await client.get(f"/api/ai/projects/{project_id}/summary")
    assert fetched.status_code == 200
    assert fetched.json()["summary"] == "Everything looks fine."


async def test_regenerate_bypasses_cooldown(client):
    project_id, _ = await _make_project_with_asset(client)
    await client.post(f"/api/ai/projects/{project_id}/summary/regenerate")

    app.dependency_overrides[get_provider] = lambda: FakeProvider("Updated summary.")
    second = await client.post(f"/api/ai/projects/{project_id}/summary/regenerate")
    assert second.status_code == 200
    assert second.json()["summary"] == "Updated summary."  # not blocked by cooldown


async def test_regenerate_unknown_project_404(client):
    response = await client.post(f"/api/ai/projects/{uuid.uuid4()}/summary/regenerate")
    assert response.status_code == 404


async def test_chat_with_project_id_includes_stored_summary_and_changes(client):
    project_id, asset_id = await _make_project_with_asset(client)
    await client.post(f"/api/ai/projects/{project_id}/summary/regenerate")
    _add_change_event(asset_id)

    provider = FakeProvider("Here's what changed.")
    app.dependency_overrides[get_provider] = lambda: provider

    response = await client.post("/api/ai/chat", json={"message": "what changed recently?", "project_id": project_id})
    assert response.status_code == 200
    assert "Everything looks fine." in provider.last_system  # the stored summary, grounded not invented
    assert "PORT_OPENED" in provider.last_system


async def test_chat_with_project_id_before_any_summary_says_so(client):
    project_id, _ = await _make_project_with_asset(client)
    provider = FakeProvider()
    app.dependency_overrides[get_provider] = lambda: provider

    response = await client.post("/api/ai/chat", json={"message": "how's this project doing?", "project_id": project_id})
    assert response.status_code == 200
    assert "No summary generated yet" in provider.last_system


async def test_chat_with_unknown_project_id_404(client):
    response = await client.post("/api/ai/chat", json={"message": "hi", "project_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_chat_never_writes_a_summary_itself(client):
    """Chat only reads AI Memory context -- it must never trigger a
    regeneration or write a ProjectAISummary row as a side effect."""
    project_id, _ = await _make_project_with_asset(client)
    provider = FakeProvider()
    app.dependency_overrides[get_provider] = lambda: provider

    await client.post("/api/ai/chat", json={"message": "hi", "project_id": project_id})

    still_missing = await client.get(f"/api/ai/projects/{project_id}/summary")
    assert still_missing.status_code == 404
