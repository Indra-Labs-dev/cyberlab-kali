import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as agent_main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402


def test_terminal_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(agent_main, "AGENT_TOKEN", "the-real-token")
    client = TestClient(agent_main.app)
    try:
        with client.websocket_connect("/terminal"):
            raise AssertionError("connection should have been rejected")
    except WebSocketDisconnect as exc:
        assert exc.code == 4401


def test_terminal_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(agent_main, "AGENT_TOKEN", "the-real-token")
    client = TestClient(agent_main.app)
    try:
        with client.websocket_connect("/terminal?token=wrong"):
            raise AssertionError("connection should have been rejected")
    except WebSocketDisconnect as exc:
        assert exc.code == 4401


def test_terminal_rejects_when_no_token_configured(monkeypatch):
    # Defense in depth: an agent started without AGENT_TOKEN set must never
    # fall back to "auth disabled" for the most privileged endpoint it has.
    monkeypatch.setattr(agent_main, "AGENT_TOKEN", "")
    client = TestClient(agent_main.app)
    try:
        with client.websocket_connect("/terminal?token="):
            raise AssertionError("connection should have been rejected")
    except WebSocketDisconnect as exc:
        assert exc.code == 4401
