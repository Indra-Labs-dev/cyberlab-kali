import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.main import app


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_auth_disabled_by_default_allows_requests():
    settings = get_settings()
    assert settings.auth_enabled is False
    async with await _client() as client:
        response = await client.get("/api/health")
    assert response.status_code == 200


async def test_health_stays_reachable_when_auth_enabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with await _client() as client:
        response = await client.get("/api/health")
    assert response.status_code == 200


async def test_protected_route_rejects_missing_token_when_auth_enabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with await _client() as client:
        response = await client.get("/api/tools")
    assert response.status_code == 401


async def test_protected_route_rejects_wrong_token_when_auth_enabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with await _client() as client:
        response = await client.get("/api/tools", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


async def test_protected_route_accepts_correct_token_when_auth_enabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with await _client() as client:
        response = await client.get(
            "/api/tools", headers={"Authorization": f"Bearer {settings.api_secret_key}"}
        )
    assert response.status_code == 200


async def test_non_api_paths_are_not_guarded(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with await _client() as client:
        response = await client.get("/docs")
    assert response.status_code != 401


def test_websocket_rejects_missing_token_when_auth_enabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    client = TestClient(app)
    try:
        with client.websocket_connect("/api/ws/jobs/00000000-0000-0000-0000-000000000000"):
            raise AssertionError("connection should have been rejected")
    except WebSocketDisconnect as exc:
        assert exc.code == 4401


@pytest.mark.parametrize(
    "path",
    [
        "/api/tools",
        "/api/jobs",
        "/api/findings",
        "/api/reports",
        "/api/reports/00000000-0000-0000-0000-000000000000/download",
        "/api/labs",
        "/api/labs/definitions",
        "/api/projects",
        "/api/projects/00000000-0000-0000-0000-000000000000",
        "/api/projects/00000000-0000-0000-0000-000000000000/targets",
        "/api/targets",
        "/api/targets/00000000-0000-0000-0000-000000000000",
        "/api/targets/00000000-0000-0000-0000-000000000000/jobs",
        "/api/projects/00000000-0000-0000-0000-000000000000/assets",
        "/api/assets",
        "/api/assets/00000000-0000-0000-0000-000000000000",
        "/api/assets/00000000-0000-0000-0000-000000000000/jobs",
        "/api/assets/00000000-0000-0000-0000-000000000000/schedules",
        "/api/assets/00000000-0000-0000-0000-000000000000/changes",
        "/api/assets/00000000-0000-0000-0000-000000000000/risk-summary",
        "/api/schedules/00000000-0000-0000-0000-000000000000",
        "/api/findings/00000000-0000-0000-0000-000000000000/risk",
        "/api/findings/00000000-0000-0000-0000-000000000000/history",
        "/api/findings/00000000-0000-0000-0000-000000000000/relations",
        "/api/findings/00000000-0000-0000-0000-000000000000/status",
        "/api/intelligence/status",
        "/api/intelligence/sync",
        "/api/graph/assets/00000000-0000-0000-0000-000000000000",
        "/api/graph/findings/00000000-0000-0000-0000-000000000000",
        "/api/graph/projects/00000000-0000-0000-0000-000000000000",
        "/api/graph/nodes/ASSET/00000000-0000-0000-0000-000000000000",
        "/api/graph/rebuild",
        "/api/ai/plan",
        "/api/ai/chat",
        "/api/ai/analyze/00000000-0000-0000-0000-000000000000",
        "/api/ai/missions",
        "/api/ai/missions/00000000-0000-0000-0000-000000000000",
        "/api/ai/missions/00000000-0000-0000-0000-000000000000/approve",
        "/api/ai/missions/00000000-0000-0000-0000-000000000000/cancel",
        "/api/ai/correlation-suggestions",
        "/api/ai/correlation-suggestions/00000000-0000-0000-0000-000000000000/accept",
        "/api/ai/correlation-suggestions/00000000-0000-0000-0000-000000000000/dismiss",
        "/api/ai/reports/propose",
        "/api/ai/projects/00000000-0000-0000-0000-000000000000/summary",
        "/api/ai/projects/00000000-0000-0000-0000-000000000000/summary/regenerate",
        "/api/chains/templates",
        "/api/chains/templates/00000000-0000-0000-0000-000000000000",
        "/api/chains/runs",
        "/api/chains/runs/00000000-0000-0000-0000-000000000000",
        "/api/chains/runs/00000000-0000-0000-0000-000000000000/cancel",
    ],
)
async def test_every_api_route_is_guarded_when_auth_enabled(monkeypatch, path):
    """Regression test for 'forgotten' endpoints: every router mounted under
    /api must be behind the auth middleware, not just the ones with explicit
    tests. The middleware guards by path prefix regardless of HTTP method, so
    a bare GET is enough to prove a POST-only route (e.g. /api/ai/plan) is
    also guarded — routing never even happens before the 401.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with await _client() as client:
        response = await client.get(path)
    assert response.status_code == 401


def test_terminal_websocket_rejects_missing_token_when_auth_enabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    client = TestClient(app)
    try:
        with client.websocket_connect("/api/ws/terminal"):
            raise AssertionError("connection should have been rejected")
    except WebSocketDisconnect as exc:
        assert exc.code == 4401


def test_websocket_accepts_token_via_query_param_when_auth_enabled(monkeypatch):
    # The job doesn't exist, so the connection is accepted (auth passes) and
    # then simply never receives any pub/sub message -- we only care that
    # auth didn't reject it outright, unlike the missing-token case above.
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    client = TestClient(app)
    with client.websocket_connect(
        f"/api/ws/jobs/00000000-0000-0000-0000-000000000000?token={settings.api_secret_key}"
    ) as ws:
        assert ws is not None
