"""Phase 23 P1.1 -- minimal rate limiting on sensitive endpoints.

Redis-backed fixed-window counters (INCR + EXPIRE on first hit), keyed by
client IP + bucket name -- reusing the Redis instance already required for
RQ, not a new dependency. Deliberately not a distributed token-bucket/
leaky-bucket system: a fixed window is simple, cheap (two Redis calls per
request), and sufficient for "a single shared-token instance shouldn't be
floodable," which is the actual threat this addresses (see docs/security.md
Phase 23 -- no rate limiting was previously a MEDIUM finding common to
every sensitive endpoint, elevated by the fact this instance can run
network-exposed).

Disabled by default (`rate_limit_enabled=False`), the same convention as
AUTH_ENABLED -- opt in together when exposing an instance beyond localhost.
Applied as a FastAPI dependency on specific routes, not a blanket
middleware: only endpoints that create real work (a Job, a report, an LLM
call) are limited, not every read-only GET.

Both `rate_limit_enabled` and the per-bucket limit are read fresh from
settings on every request (not captured once when the dependency is built)
-- Settings() is a normal mutable object behind `get_settings()`'s
lru_cache, and tests toggle individual fields on it via monkeypatch
(mirroring tests/test_auth_middleware.py's `monkeypatch.setattr(settings,
"auth_enabled", True)` idiom); capturing values at import time would make
that pattern silently not work here.
"""

from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.jobs.queue import get_redis_connection

_KEY_PREFIX = "cyberlab:ratelimit"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def rate_limit(bucket: str, limit_attr: str):
    """Returns a FastAPI dependency enforcing `getattr(settings, limit_attr)`
    requests per `settings.rate_limit_window_seconds` per client IP, for
    this bucket. `limit_attr` is the Settings field name (not a resolved
    int) so the limit is re-read fresh on every request.
    """

    async def _dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        max_requests: int = getattr(settings, limit_attr)
        window = settings.rate_limit_window_seconds
        key = f"{_KEY_PREFIX}:{bucket}:{_client_ip(request)}"
        redis = get_redis_connection()
        current = redis.incr(key)
        if current == 1:
            redis.expire(key, window)

        if current > max_requests:
            ttl = redis.ttl(key)
            retry_after = ttl if ttl and ttl > 0 else window
            raise HTTPException(
                status_code=429,
                detail=(
                    f"rate limit exceeded: max {max_requests} requests per "
                    f"{window}s for this endpoint, try again in {retry_after}s"
                ),
                headers={"Retry-After": str(retry_after)},
            )

    return _dependency


# One dependency instance per bucket, reused across every route in that
# bucket (e.g. all 4 Job-creation call sites that go through POST
# /api/jobs) -- built once at import time, but see the docstring above for
# why that's safe: only the *bucket wiring* is fixed at import time, the
# enabled flag and the limit value itself are read fresh per request.
job_creation_limit = rate_limit("job_creation", "rate_limit_job_creation_per_window")
chain_run_limit = rate_limit("chain_run", "rate_limit_chain_run_per_window")
report_generation_limit = rate_limit("report_generation", "rate_limit_report_generation_per_window")
ai_call_limit = rate_limit("ai_call", "rate_limit_ai_call_per_window")
