import httpx

from app.core.config import get_settings


class KaliAgentError(RuntimeError):
    pass


def run_tool(tool: str, args: list[str], timeout: int = 60) -> dict:
    settings = get_settings()
    try:
        response = httpx.post(
            f"{settings.kali_agent_url}/exec",
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
