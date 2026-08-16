import logging

import httpx

from app.core.config import get_settings
from app.jobs.queue import get_redis_connection

logger = logging.getLogger("cyberlab.jobs.kali_client")

# Multi-Kali opt-in (roadmap §8) -- a per-URL count of requests currently
# in flight, tracked in the same Redis instance RQ already requires (never
# a new dependency). Not real CPU/queue-depth telemetry -- the Kali agent
# exposes none (see docs/phase-multi-kali.md's rationale for not adding
# one, "10% of the cost") -- but a genuine, testable "currently busier
# than its siblings" signal, not blind round-robin.
_BUSY_KEY_PREFIX = "cyberlab:kali:busy"

# Post-audit fix (Multi-Kali x Plugin System) -- how long a compatibility
# check against one agent's /health is allowed to take. Short: this runs
# synchronously before every multi-instance dispatch, and an unreachable
# agent must not stall job dispatch waiting on it.
_HEALTH_CHECK_TIMEOUT_SECONDS = 5.0


class KaliAgentError(RuntimeError):
    pass


def _agent_has_tool(url: str, tool: str) -> bool:
    """Queries one agent's own advertised tool inventory (/health,
    unauthenticated, already existed for Multi-Kali's own health checks --
    no new endpoint). An unreachable agent is treated as incompatible, not
    fatal: it is simply excluded from selection, same spirit as the busy
    counter being decremented even on failure -- one bad instance must
    never block dispatch to the others.
    """
    try:
        response = httpx.get(f"{url}/health", timeout=_HEALTH_CHECK_TIMEOUT_SECONDS)
        response.raise_for_status()
        tools_available = response.json().get("tools_available", [])
    except httpx.HTTPError:
        logger.warning("kali agent unreachable during tool-compatibility check, excluded from selection: %s", url)
        return False
    return tool in tools_available


def _select_agent_url(urls: list[str], tool: str) -> str:
    """Exactly today's single value when only one URL is configured -- no
    Redis touched at all, zero behavior or performance change for the
    default, non-opted-in case (see Settings.kali_agent_urls).

    Post-audit fix (Multi-Kali x Plugin System): with more than one
    configured instance, `_select_agent_url` used to assume every instance
    could run every tool -- true by construction for the 31 curated tools
    baked into the shared Kali image, but not for Plugin System's
    EXTRA_ALLOWED_TOOLS, which is set per-container. A plugin tool
    available on only one instance could previously be routed to another
    instance that would reject it, a job failure that depended on load at
    dispatch time rather than on whether the tool could actually run
    there. Now, only instances that actually advertise the requested tool
    are eligible; load-based ranking (unchanged) applies among those.
    Since curated tools are present on every instance by construction,
    this filter is always a no-op for them -- selection outcome for the
    31 curated tools is unchanged.
    """
    if len(urls) == 1:
        return urls[0]
    compatible = [url for url in urls if _agent_has_tool(url, tool)]
    if not compatible:
        raise KaliAgentError(f"no configured Kali agent instance has tool {tool!r} available")
    if len(compatible) == 1:
        return compatible[0]
    redis = get_redis_connection()
    counts = redis.mget([f"{_BUSY_KEY_PREFIX}:{url}" for url in compatible])
    ranked = sorted(zip(compatible, counts), key=lambda pair: int(pair[1] or 0))
    return ranked[0][0]


def get_tool_health() -> list[dict]:
    """Deliberately checks only the primary kali_agent_url, never every
    configured instance -- all replicas run the identical image (see
    docker-compose.yml), so tool availability is the same across them by
    construction; this is a documented simplification, not a functional
    gap in job dispatch itself (see docs/phase-multi-kali.md).
    """
    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.kali_agent_url}/health/tools",
            headers={"X-Agent-Token": settings.kali_agent_token},
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise KaliAgentError(f"kali agent unreachable: {exc}") from exc
    return response.json()


def run_tool(tool: str, args: list[str], timeout: int = 60) -> dict:
    settings = get_settings()
    urls = settings.kali_agent_urls
    multi = len(urls) > 1
    url = _select_agent_url(urls, tool)

    redis = get_redis_connection() if multi else None
    busy_key = f"{_BUSY_KEY_PREFIX}:{url}"
    if redis is not None:
        redis.incr(busy_key)
    try:
        try:
            response = httpx.post(
                f"{url}/exec",
                json={"tool": tool, "args": args, "timeout": timeout},
                headers={"X-Agent-Token": settings.kali_agent_token},
                timeout=timeout + 10,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KaliAgentError(f"kali agent rejected request: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise KaliAgentError(f"kali agent unreachable: {exc}") from exc
        return response.json()
    finally:
        # Always decremented -- success, tool error, or agent unreachable
        # -- so a failed/timed-out call never leaves this instance
        # permanently looking busier than it really is.
        if redis is not None:
            redis.decr(busy_key)
