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


def _health_response(tools_available: list[str]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"status": "ok", "tools_available": tools_available}
    return response


def test_select_agent_url_returns_the_single_configured_url_without_redis():
    # Single-URL case never touches Redis NOR queries /health -- exactly
    # today's zero-overhead behavior for the default, non-opted-in case.
    with patch("app.jobs.kali_client.httpx.get") as mock_get:
        assert _select_agent_url(["http://only:9000"], "nmap") == "http://only:9000"
    mock_get.assert_not_called()


async def test_select_agent_url_picks_the_least_busy_instance_among_compatible_agents():
    """Curated tool present on every instance (by construction) -- the
    compatibility filter is a no-op, load-based selection is unchanged."""
    _flush_busy_keys()
    redis = get_redis_connection()
    urls = ["http://a:9000", "http://b:9000", "http://c:9000"]
    redis.set(f"cyberlab:kali:busy:{urls[0]}", 3)
    redis.set(f"cyberlab:kali:busy:{urls[1]}", 0)
    redis.set(f"cyberlab:kali:busy:{urls[2]}", 1)

    with patch("app.jobs.kali_client.httpx.get", return_value=_health_response(["nmap", "nikto"])):
        assert _select_agent_url(urls, "nmap") == urls[1]


async def test_select_agent_url_treats_unset_counters_as_zero():
    _flush_busy_keys()
    urls = ["http://a:9000", "http://b:9000"]
    redis = get_redis_connection()
    redis.set(f"cyberlab:kali:busy:{urls[0]}", 5)
    # urls[1] has no key at all -- must be treated as 0, not skipped/errored.

    with patch("app.jobs.kali_client.httpx.get", return_value=_health_response(["nmap"])):
        assert _select_agent_url(urls, "nmap") == urls[1]


async def test_select_agent_url_excludes_an_instance_missing_the_plugin_tool():
    """Post-audit fix -- a plugin tool available on only kali-1 must never
    be routed to kali-2, even if kali-2 is far less busy."""
    _flush_busy_keys()
    redis = get_redis_connection()
    urls = ["http://kali-1:9000", "http://kali-2:9000"]
    redis.set(f"cyberlab:kali:busy:{urls[0]}", 5)  # kali-1 busier...
    redis.set(f"cyberlab:kali:busy:{urls[1]}", 0)  # ...but kali-2 lacks the plugin.

    def _health(url, **kwargs):
        if url == "http://kali-1:9000/health":
            return _health_response(["nmap", "myplugin"])
        return _health_response(["nmap"])  # kali-2: curated tools only

    with patch("app.jobs.kali_client.httpx.get", side_effect=_health):
        assert _select_agent_url(urls, "myplugin") == "http://kali-1:9000"


async def test_select_agent_url_load_balances_among_compatible_instances_when_plugin_is_everywhere():
    _flush_busy_keys()
    redis = get_redis_connection()
    urls = ["http://kali-1:9000", "http://kali-2:9000"]
    redis.set(f"cyberlab:kali:busy:{urls[0]}", 5)
    redis.set(f"cyberlab:kali:busy:{urls[1]}", 1)  # less busy, must win

    with patch("app.jobs.kali_client.httpx.get", return_value=_health_response(["myplugin"])):
        assert _select_agent_url(urls, "myplugin") == "http://kali-2:9000"


async def test_select_agent_url_raises_deterministic_error_when_no_instance_has_the_tool():
    urls = ["http://kali-1:9000", "http://kali-2:9000"]
    with patch("app.jobs.kali_client.httpx.get", return_value=_health_response(["nmap"])):
        with pytest.raises(KaliAgentError, match="nowhere-tool"):
            _select_agent_url(urls, "nowhere-tool")


async def test_select_agent_url_error_message_leaks_no_secrets():
    """The error is shown to operators (Job.error) -- it must never
    contain the shared agent token or raw response bodies, only the tool
    name, which the caller already knows."""
    urls = ["http://kali-1:9000", "http://kali-2:9000"]
    settings = get_settings()
    message = None
    with patch("app.jobs.kali_client.httpx.get", return_value=_health_response([])):
        try:
            _select_agent_url(urls, "nowhere-tool")
        except KaliAgentError as exc:
            message = str(exc)
    assert message is not None
    assert settings.kali_agent_token not in message
    assert "http://kali-1:9000" not in message
    assert "http://kali-2:9000" not in message


async def test_select_agent_url_treats_an_unreachable_instance_as_incompatible():
    """An agent that can't even answer /health must be excluded from
    selection, not crash the whole dispatch -- same isolation spirit as
    the rest of Multi-Kali's failure handling."""
    import httpx

    urls = ["http://unreachable:9000", "http://kali-2:9000"]

    def _health(url, **kwargs):
        if url == "http://unreachable:9000/health":
            raise httpx.ConnectError("connection refused")
        return _health_response(["myplugin"])

    with patch("app.jobs.kali_client.httpx.get", side_effect=_health):
        assert _select_agent_url(urls, "myplugin") == "http://kali-2:9000"


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

    with patch("app.jobs.kali_client.httpx.get", return_value=_health_response(["nmap"])):
        with patch("app.jobs.kali_client.httpx.post", side_effect=_capture_post) as mock_post:
            run_tool("nmap", ["-sV", "target"])

    assert mock_post.call_args.args[0] == "http://a:9000/exec"
    assert seen_during_call["a"] == 1  # incremented before dispatch
    assert int(redis.get("cyberlab:kali:busy:http://a:9000")) == 0  # decremented after


async def test_run_tool_curated_tool_behavior_is_unchanged_end_to_end(monkeypatch):
    """Requirement: '31 outils curatés -> comportement inchangé', proven
    through the full run_tool() path, not just _select_agent_url() in
    isolation. Both instances advertise the curated tool (true by
    construction, mirrored here explicitly) -- the outcome must be
    identical to the pre-fix, load-only selection."""
    _flush_busy_keys()
    settings = get_settings()
    monkeypatch.setattr(settings, "kali_agent_urls_raw", "http://a:9000,http://b:9000")
    redis = get_redis_connection()
    redis.set("cyberlab:kali:busy:http://a:9000", 2)
    redis.set("cyberlab:kali:busy:http://b:9000", 0)

    with patch("app.jobs.kali_client.httpx.get", return_value=_health_response(["nmap", "nikto", "sqlmap"])):
        with patch("app.jobs.kali_client.httpx.post", return_value=_ok_response()) as mock_post:
            result = run_tool("nmap", ["-sV", "target"])

    assert result == {"stdout": "ok", "stderr": "", "exit_code": 0}
    assert mock_post.call_args.args[0] == "http://b:9000/exec"


async def test_run_tool_multi_url_decrements_even_when_the_agent_call_fails(monkeypatch):
    _flush_busy_keys()
    settings = get_settings()
    monkeypatch.setattr(settings, "kali_agent_urls_raw", "http://a:9000,http://b:9000")

    with patch("app.jobs.kali_client.httpx.get", return_value=_health_response(["nmap"])):
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
