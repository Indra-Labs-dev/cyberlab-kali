"""Multi-Kali opt-in (roadmap §8) -- app/jobs/kali_client.py. httpx itself
is mocked (no precedent for this in the existing Kali tests, which all
patch at the app.jobs.tasks import boundary instead -- this file tests
kali_client.py directly, so the HTTP layer is the right place to cut).
The Redis busy-counter is real (same instance RQ already requires),
flushed per test the same way tests/test_rate_limit.py's own counters are.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.jobs.kali_client import KaliAgentError, _select_agent_url, run_tool
from app.jobs.queue import get_redis_connection


def _flush_busy_keys() -> None:
    redis = get_redis_connection()
    for key in redis.scan_iter(match="cyberlab:kali:busy:*"):
        redis.delete(key)


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}
    return response


async def test_run_tool_single_url_never_touches_redis(monkeypatch):
    """The default, non-opted-in case: exactly today's behavior, zero
    Redis overhead."""
    settings = get_settings()
    monkeypatch.setattr(settings, "kali_agent_urls_raw", "")

    with patch("app.jobs.kali_client.httpx.post", return_value=_ok_response()) as mock_post:
        with patch("app.jobs.kali_client.get_redis_connection") as mock_get_redis:
            result = run_tool("nmap", ["-sV", "target"])

    assert result == {"stdout": "ok", "stderr": "", "exit_code": 0}
    mock_get_redis.assert_not_called()
    assert mock_post.call_args.args[0] == f"{settings.kali_agent_url}/exec"


def test_select_agent_url_returns_the_single_configured_url_without_redis():
    assert _select_agent_url(["http://only:9000"]) == "http://only:9000"


async def test_select_agent_url_picks_the_least_busy_instance():
    _flush_busy_keys()
    redis = get_redis_connection()
    urls = ["http://a:9000", "http://b:9000", "http://c:9000"]
    redis.set(f"cyberlab:kali:busy:{urls[0]}", 3)
    redis.set(f"cyberlab:kali:busy:{urls[1]}", 0)
    redis.set(f"cyberlab:kali:busy:{urls[2]}", 1)

    assert _select_agent_url(urls) == urls[1]


async def test_select_agent_url_treats_unset_counters_as_zero():
    _flush_busy_keys()
    urls = ["http://a:9000", "http://b:9000"]
    redis = get_redis_connection()
    redis.set(f"cyberlab:kali:busy:{urls[0]}", 5)
    # urls[1] has no key at all -- must be treated as 0, not skipped/errored.

    assert _select_agent_url(urls) == urls[1]


async def test_run_tool_multi_url_increments_then_decrements_around_a_successful_call(monkeypatch):
    _flush_busy_keys()
    settings = get_settings()
    monkeypatch.setattr(settings, "kali_agent_urls_raw", "http://a:9000,http://b:9000")
    redis = get_redis_connection()
    redis.set("cyberlab:kali:busy:http://a:9000", 0)
    redis.set("cyberlab:kali:busy:http://b:9000", 5)  # b is busier -- a must be chosen

    seen_during_call = {}

    def _capture_post(url, **kwargs):
        # The busy count must be incremented BEFORE the HTTP call is made,
        # not after -- otherwise a concurrent selection could race onto the
        # same "least busy" instance while this call is still in flight.
        seen_during_call["a"] = int(redis.get("cyberlab:kali:busy:http://a:9000"))
        return _ok_response()

    with patch("app.jobs.kali_client.httpx.post", side_effect=_capture_post) as mock_post:
        run_tool("nmap", ["-sV", "target"])

    assert mock_post.call_args.args[0] == "http://a:9000/exec"
    assert seen_during_call["a"] == 1  # incremented before dispatch
    assert int(redis.get("cyberlab:kali:busy:http://a:9000")) == 0  # decremented after


async def test_run_tool_multi_url_decrements_even_when_the_agent_call_fails(monkeypatch):
    _flush_busy_keys()
    settings = get_settings()
    monkeypatch.setattr(settings, "kali_agent_urls_raw", "http://a:9000,http://b:9000")

    with patch("app.jobs.kali_client.httpx.post", side_effect=RuntimeError("connection refused")):
        with pytest.raises(RuntimeError):
            run_tool("nmap", ["-sV", "target"])

    redis = get_redis_connection()
    # Never left permanently "busier" than reality after a failed call.
    assert int(redis.get("cyberlab:kali:busy:http://a:9000") or 0) == 0
    assert int(redis.get("cyberlab:kali:busy:http://b:9000") or 0) == 0


async def test_run_tool_wraps_http_errors_as_kali_agent_error(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "kali_agent_urls_raw", "")
    response = MagicMock()
    response.text = "bad request"
    import httpx

    with patch("app.jobs.kali_client.httpx.post", side_effect=httpx.HTTPStatusError("boom", request=MagicMock(), response=response)):
        with pytest.raises(KaliAgentError):
            run_tool("nmap", ["-sV", "target"])
