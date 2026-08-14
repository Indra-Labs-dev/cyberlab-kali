"""Phase 23 P1.1 -- app/core/rate_limit.py, real HTTP + real Redis (the
same instance RQ already uses). Disabled by default (rate_limit_enabled=
False), same convention as AUTH_ENABLED -- these tests explicitly
monkeypatch it on, mirroring tests/test_auth_middleware.py's idiom, and
flush the specific Redis keys they touch first so they never depend on
(or pollute) another test's counter state.
"""

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
