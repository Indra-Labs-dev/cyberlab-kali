import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@router.get("/health/kali")
async def health_kali() -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{settings.kali_agent_url}/health")
            response.raise_for_status()
            return {"status": "ok", **response.json()}
    except httpx.HTTPError:
        return {"status": "unreachable"}


@router.get("/health/ollama")
async def health_ollama() -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{settings.ollama_url}/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
            return {"status": "ok", "models": models}
    except httpx.HTTPError:
        return {"status": "unreachable"}
