from httpx import ASGITransport, AsyncClient

from app.jobs.kali_client import KaliAgentError
from app.main import app
from app.tools import registry


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_tools_health_merges_agent_report_with_full_registry(monkeypatch):
    # The agent only reports tools it actually resolved via shutil.which --
    # simulate it knowing about nmap but nothing else, and confirm every
    # other registered tool still shows up as "not_installed" rather than
    # being silently dropped from the response.
    def fake_health():
        return [{"name": "nmap", "status": "ready", "detail": "Nmap version 7.9"}]

    monkeypatch.setattr("app.api.routes.tools.get_tool_health", fake_health)

    async with await _client() as client:
        response = await client.get("/api/tools/health")

    assert response.status_code == 200
    body = {entry["name"]: entry for entry in response.json()}
    all_tool_names = {tool.name for tool in registry.list_tools()}
    assert set(body.keys()) == all_tool_names
    assert body["nmap"]["status"] == "ready"
    other_tool = next(name for name in all_tool_names if name != "nmap")
    assert body[other_tool]["status"] == "not_installed"


async def test_tools_health_reports_unknown_when_agent_unreachable(monkeypatch):
    def fake_health():
        raise KaliAgentError("kali agent unreachable: connection refused")

    monkeypatch.setattr("app.api.routes.tools.get_tool_health", fake_health)

    async with await _client() as client:
        response = await client.get("/api/tools/health")

    assert response.status_code == 200
    body = response.json()
    assert body
    assert all(entry["status"] == "unknown" for entry in body)


async def test_tools_health_route_registered_before_name_route():
    # Regression guard: /tools/health must never be shadowed by /tools/{name}
    # matching "health" as a tool name lookup (which would 404).
    async with await _client() as client:
        response = await client.get("/api/tools/health")
    assert response.status_code == 200
