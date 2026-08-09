from fastapi import APIRouter, HTTPException

from app.tools import registry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def list_tools() -> list[dict]:
    return [tool.model_dump() for tool in registry.list_tools()]


@router.get("/{name}")
async def get_tool(name: str) -> dict:
    try:
        return registry.get_tool(name).model_dump()
    except registry.ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
