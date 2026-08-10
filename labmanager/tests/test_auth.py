import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as labmanager_main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_list_labs_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(labmanager_main, "AGENT_TOKEN", "the-real-token")
    client = TestClient(labmanager_main.app)
    response = client.get("/labs")
    assert response.status_code == 401


def test_list_labs_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(labmanager_main, "AGENT_TOKEN", "the-real-token")
    client = TestClient(labmanager_main.app)
    response = client.get("/labs", headers={"X-Agent-Token": "wrong"})
    assert response.status_code == 401


def test_list_labs_rejects_when_no_token_configured(monkeypatch):
    monkeypatch.setattr(labmanager_main, "AGENT_TOKEN", "")
    client = TestClient(labmanager_main.app)
    response = client.get("/labs", headers={"X-Agent-Token": ""})
    assert response.status_code == 401


def test_list_labs_accepts_correct_token(monkeypatch):
    monkeypatch.setattr(labmanager_main, "AGENT_TOKEN", "the-real-token")
    with patch("docker_manager.list_labs", return_value=[]):
        client = TestClient(labmanager_main.app)
        response = client.get("/labs", headers={"X-Agent-Token": "the-real-token"})
    assert response.status_code == 200
    assert response.json() == []


def test_create_lab_unknown_definition_returns_404(monkeypatch):
    monkeypatch.setattr(labmanager_main, "AGENT_TOKEN", "the-real-token")
    client = TestClient(labmanager_main.app)
    response = client.post(
        "/labs", params={"definition": "not-a-real-lab"}, headers={"X-Agent-Token": "the-real-token"}
    )
    assert response.status_code == 404
