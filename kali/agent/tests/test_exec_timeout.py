import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as agent_main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_exec_handles_timeout_with_bytes_stderr(monkeypatch):
    """Regression test for a real crash found via Phase 12 end-to-end
    testing: subprocess.TimeoutExpired.stdout/.stderr can come back as bytes
    even with text=True, and the handler used to do `bytes_value + "str"`,
    crashing the whole /exec call with a 500 instead of reporting a timeout.
    """
    monkeypatch.setattr(agent_main, "AGENT_TOKEN", "test-token")
    monkeypatch.setattr(agent_main, "ALLOWED_TOOLS", {"faketool": "/usr/bin/faketool"})

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["faketool"], timeout=1, output=b"partial stdout", stderr=b"partial stderr")

    monkeypatch.setattr(agent_main.subprocess, "run", _raise_timeout)

    client = TestClient(agent_main.app)
    response = client.post(
        "/exec",
        json={"tool": "faketool", "args": [], "timeout": 1},
        headers={"X-Agent-Token": "test-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["timed_out"] is True
    assert body["exit_code"] == -1
    assert body["stdout"] == "partial stdout"
    assert "partial stderr" in body["stderr"]
    assert "[cyberlab] process killed after timeout" in body["stderr"]
