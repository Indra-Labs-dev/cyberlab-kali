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

import logging

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger("cyberlab.rate_limit")

_KEY_PREFIX = "cyberlab:ratelimit"

# No configured recovery time is known when Redis is unreachable -- this is
# just a short, honest hint for well-behaved clients, not a promise.
_UNAVAILABLE_RETRY_AFTER_SECONDS = 5


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _build_redis_client(settings) -> Redis:
    """A dedicated client, deliberately NOT app.jobs.queue.get_redis_
    connection()'s shared, timeout-less singleton (used by RQ's worker for
    blocking dequeue and by pubsub) -- imposing a short timeout on that
    shared connection would risk changing worker/pubsub behavior, which is
    out of scope here. Built fresh per call (redis-py doesn't open a socket
    until the first command, so this costs no connection overhead) rather
    than cached, so it keeps reading settings.redis_url/settings.
    rate_limit_redis_timeout_seconds fresh on every request -- the same
    "never capture settings at import time" reasoning already applied to
    rate_limit_enabled and the per-bucket limit below.
    """
    timeout = settings.rate_limit_redis_timeout_seconds
    return Redis.from_url(settings.redis_url, socket_connect_timeout=timeout, socket_timeout=timeout)


def rate_limit(bucket: str, limit_attr: str):
    """Returns a FastAPI dependency enforcing `getattr(settings, limit_attr)`
    requests per `settings.rate_limit_window_seconds` per client IP, for
    this bucket. `limit_attr` is the Settings field name (not a resolved
    int) so the limit is re-read fresh on every request.

    Fails closed if Redis is unreachable: a 503, bounded by the short
    timeout above, never a 429 (which would falsely claim the caller is
    over a limit that was never actually checked) and never an indefinite
    hang on the OS's own TCP timeout. RATE_LIMIT_ENABLED is an explicit
    opt-in for instances exposed beyond localhost (see module docstring);
    silently letting every request through the moment Redis blips would
    defeat the reason it was turned on in the first place. This applies
    uniformly to every bucket, including the two (report_generation,
    ai_call) whose own route handlers never touch Redis -- a deliberate
    trade of a small, bounded availability cost during a rare Redis outage
    for one predictable rule instead of a per-bucket policy matrix.
    """

    async def _dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        max_requests: int = getattr(settings, limit_attr)
        window = settings.rate_limit_window_seconds
        key = f"{_KEY_PREFIX}:{bucket}:{_client_ip(request)}"

        try:
            redis = _build_redis_client(settings)
            current = redis.incr(key)
            if current == 1:
                redis.expire(key, window)
            over_limit = current > max_requests
            retry_after = redis.ttl(key) if over_limit else None
        except RedisError as exc:
            # Exception type only, never str(exc) -- redis-py error messages
            # can echo back the connection target, and settings.redis_url
            # may carry credentials in a non-default deployment.
            logger.error("rate limiter: redis unavailable for bucket %r (%s)", bucket, type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="rate limiting is temporarily unavailable; try again shortly",
                headers={"Retry-After": str(_UNAVAILABLE_RETRY_AFTER_SECONDS)},
            ) from None

        if over_limit:
            retry_after = retry_after if retry_after and retry_after > 0 else window
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
