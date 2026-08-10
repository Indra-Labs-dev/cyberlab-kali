from fastapi import APIRouter, HTTPException

from app.jobs.kali_client import KaliAgentError, get_tool_health
from app.tools import registry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def list_tools() -> list[dict]:
    return [tool.model_dump() for tool in registry.list_tools()]


# Registered before /{name} -- otherwise FastAPI would match "health" as a
# tool name and 404 through get_tool() instead of reaching this handler.
@router.get("/health")
async def tools_health() -> list[dict]:
    """Non-destructive per-tool invocation check (--version/--help probes,
    never a real scan -- see kali/agent/main.py::_check_tool_health). A tool
    registered here but missing from the agent's own report (agent
    unreachable, or the executable genuinely isn't installed) is reported as
    "not_installed" rather than silently omitted.
    """
    try:
        agent_results = {r["name"]: r for r in get_tool_health()}
        agent_reachable = True
    except KaliAgentError:
        agent_results = {}
        agent_reachable = False

    results = []
    for tool in registry.list_tools():
        agent_result = agent_results.get(tool.name)
        if agent_result is not None:
            status, detail = agent_result["status"], agent_result["detail"]
        elif not agent_reachable:
            status, detail = "unknown", "Kali agent unreachable"
        else:
            status, detail = "not_installed", None
        results.append({"name": tool.name, "status": status, "detail": detail})
    return results


@router.get("/{name}")
async def get_tool(name: str) -> dict:
    try:
        return registry.get_tool(name).model_dump()
    except registry.ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
