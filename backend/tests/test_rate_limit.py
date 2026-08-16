"""Phase 23 P1.1 -- app/core/rate_limit.py, real HTTP + real Redis (the
same instance RQ already uses). Disabled by default (rate_limit_enabled=
False), same convention as AUTH_ENABLED -- these tests explicitly
monkeypatch it on, mirroring tests/test_auth_middleware.py's idiom, and
flush the specific Redis keys they touch first so they never depend on
(or pollute) another test's counter state.

Post-Phase-23 consolidation (D.1) -- the tests below at the bottom of this
file cover the Redis-unavailable path. They point settings.redis_url at a
genuinely broken target (a closed port, or a real socket that accepts but
never answers) rather than mocking redis.Redis.incr()'s return value: the
property being proven is that the *actual* redis-py client, with the
*actual* configured timeout, fails fast against a *real* dead endpoint --
not just that the except branch is reachable.
"""

import socket
import threading
import time

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.jobs.queue import get_redis_connection
from app.main import app


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _flush_bucket(bucket: str) -> None:
    redis = get_redis_connection()
    for key in redis.scan_iter(match=f"cyberlab:ratelimit:{bucket}:*"):
        redis.delete(key)


async def test_disabled_by_default_never_limits():
    settings = get_settings()
    assert settings.rate_limit_enabled is False
    _flush_bucket("job_creation")

    async with await _client() as client:
        # Well over any configured limit, but disabled -- none should 429.
        responses = [
            await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"}) for _ in range(50)
        ]
    assert all(r.status_code != 429 for r in responses)


async def test_enabled_allows_requests_under_the_limit(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_job_creation_per_window", 5)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    _flush_bucket("job_creation")

    async with await _client() as client:
        responses = [
            await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"}) for _ in range(5)
        ]
    assert all(r.status_code != 429 for r in responses)


async def test_enabled_rejects_requests_over_the_limit_with_429_and_retry_after(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_job_creation_per_window", 3)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    _flush_bucket("job_creation")

    async with await _client() as client:
        responses = [
            await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"}) for _ in range(5)
        ]

    statuses = [r.status_code for r in responses]
    assert statuses[:3] == [404, 404, 404]  # unknown tool, but under the limit -- reaches the real handler
    assert statuses[3:] == [429, 429]
    assert "Retry-After" in responses[3].headers
    assert int(responses[3].headers["Retry-After"]) > 0


async def test_rate_limit_buckets_are_independent():
    """Exhausting the job_creation bucket must never affect the
    report_generation bucket -- each route has its own counter key."""
    settings = get_settings()
    settings.rate_limit_enabled = True
    settings.rate_limit_job_creation_per_window = 1
    settings.rate_limit_report_generation_per_window = 5
    settings.rate_limit_window_seconds = 60
    _flush_bucket("job_creation")
    _flush_bucket("report_generation")

    try:
        async with await _client() as client:
            await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"})
            blocked = await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"})
            assert blocked.status_code == 429

            reports_response = await client.post(
                "/api/reports",
                json={"title": "t", "job_ids": ["00000000-0000-0000-0000-000000000000"], "format": "json"},
            )
            assert reports_response.status_code != 429  # 404 (no matching job), not rate-limited
    finally:
        settings.rate_limit_enabled = False
        settings.rate_limit_job_creation_per_window = 30
        settings.rate_limit_report_generation_per_window = 10
        settings.rate_limit_window_seconds = 60


async def test_get_routes_are_never_rate_limited(monkeypatch):
    # Sanity check that rate limiting is opt-in per-route (dependencies=[...]
    # on the specific POST handlers), not a blanket middleware -- GET routes
    # never carry the dependency at all, regardless of how low the limit is.
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_job_creation_per_window", 1)

    async with await _client() as client:
        for _ in range(5):
            response = await client.get("/api/jobs")
            assert response.status_code != 429


def _start_black_hole_server() -> tuple[int, socket.socket]:
    """A real TCP listener that completes the handshake but never reads or
    writes anything -- simulates Redis being up-but-wedged (as opposed to
    simply absent), exercising socket_timeout rather than
    socket_connect_timeout."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept_and_stall() -> None:
        try:
            conn, _ = srv.accept()
        except OSError:
            return  # server was closed before a connection arrived
        try:
            time.sleep(10)  # long enough to outlast every test's short timeout
        finally:
            conn.close()

    threading.Thread(target=_accept_and_stall, daemon=True).start()
    return port, srv


async def test_redis_connection_refused_returns_503_fast(monkeypatch):
    """Nothing listening on this port -- redis-py's connect() gets a real,
    immediate ECONNREFUSED from a genuinely absent server, not a mocked
    exception."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(settings, "rate_limit_redis_timeout_seconds", 1.0)

    started = time.monotonic()
    async with await _client() as client:
        response = await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"})
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert "Retry-After" in response.headers
    assert elapsed < 2.0  # nowhere near an OS-default TCP timeout (often 60s+)


async def test_redis_unresponsive_times_out_and_returns_503_fast(monkeypatch):
    """A real socket that completes the TCP handshake but never answers --
    proves socket_timeout (not just socket_connect_timeout) is honored, and
    that the request fails within the configured budget instead of hanging
    indefinitely waiting for a response that will never arrive."""
    port, srv = _start_black_hole_server()
    try:
        settings = get_settings()
        monkeypatch.setattr(settings, "rate_limit_enabled", True)
        monkeypatch.setattr(settings, "redis_url", f"redis://127.0.0.1:{port}/0")
        monkeypatch.setattr(settings, "rate_limit_redis_timeout_seconds", 0.5)

        started = time.monotonic()
        async with await _client() as client:
            response = await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"})
        elapsed = time.monotonic() - started

        assert response.status_code == 503
        assert "Retry-After" in response.headers
        # Bounded by the configured timeout (0.5s) plus normal overhead --
        # not the tens of seconds an unbounded socket read would otherwise take.
        assert elapsed < 3.0
    finally:
        srv.close()


async def test_redis_unavailable_response_does_not_leak_connection_details(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(settings, "rate_limit_redis_timeout_seconds", 1.0)

    async with await _client() as client:
        response = await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"})

    assert response.status_code == 503
    body = response.text.lower()
    assert "127.0.0.1:1" not in body
    assert "redis://" not in body


async def test_redis_unavailable_fails_closed_on_every_bucket(monkeypatch):
    """Not just job_creation -- report_generation and ai_call never touch
    Redis/RQ in their own handlers, so this is the one case where fail-open
    vs fail-closed is a real, deliberate trade rather than a formality (see
    the rate_limit() docstring in app/core/rate_limit.py)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(settings, "rate_limit_redis_timeout_seconds", 1.0)

    async with await _client() as client:
        job_response = await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"})
        report_response = await client.post(
            "/api/reports",
            json={"title": "t", "job_ids": ["00000000-0000-0000-0000-000000000000"], "format": "json"},
        )
        chat_response = await client.post("/api/ai/chat", json={"message": "hello"})

    assert job_response.status_code == 503
    assert report_response.status_code == 503
    assert chat_response.status_code == 503


async def test_redis_recovers_after_being_unavailable(monkeypatch):
    """Once Redis is reachable again, the very next request behaves
    normally -- the failure path leaves no lingering broken state (no
    cached dead connection, no stuck counter, no exhausted retry budget)."""
    settings = get_settings()
    original_redis_url = settings.redis_url
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_redis_timeout_seconds", 1.0)
    monkeypatch.setattr(settings, "rate_limit_job_creation_per_window", 30)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    _flush_bucket("job_creation")

    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    async with await _client() as client:
        broken = await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"})
    assert broken.status_code == 503

    monkeypatch.setattr(settings, "redis_url", original_redis_url)
    async with await _client() as client:
        recovered = await client.post("/api/jobs", json={"tool": "metasploit", "target": "127.0.0.1"})
    assert recovered.status_code != 503
    assert recovered.status_code != 429
