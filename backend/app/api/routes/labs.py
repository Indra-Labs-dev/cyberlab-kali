import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import get_settings

router = APIRouter(prefix="/labs", tags=["labs"])


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        base_url=settings.labmanager_url,
        headers={"X-Agent-Token": settings.labmanager_token},
        # Creating/resetting a lab can involve a first-time image pull, which
        # can take minutes; the labmanager itself now offloads Docker SDK
        # calls to a thread so it stays responsive to other requests meanwhile.
        timeout=600,
    )


async def _proxy(method: str, path: str, **kwargs):
    try:
        async with _client() as client:
            response = await client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"lab manager unreachable: {exc}") from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    return response


@router.get("/definitions")
async def list_definitions() -> list[dict]:
    response = await _proxy("GET", "/definitions")
    return response.json()


@router.get("")
async def list_labs() -> list[dict]:
    response = await _proxy("GET", "/labs")
    return response.json()


@router.post("", status_code=201)
async def create_lab(definition: str) -> dict:
    response = await _proxy("POST", "/labs", params={"definition": definition})
    return response.json()


@router.get("/{lab_id}")
async def get_lab(lab_id: str) -> dict:
    response = await _proxy("GET", f"/labs/{lab_id}")
    return response.json()


@router.post("/{lab_id}/start")
async def start_lab(lab_id: str) -> dict:
    response = await _proxy("POST", f"/labs/{lab_id}/start")
    return response.json()


@router.post("/{lab_id}/stop")
async def stop_lab(lab_id: str) -> dict:
    response = await _proxy("POST", f"/labs/{lab_id}/stop")
    return response.json()


@router.post("/{lab_id}/reset")
async def reset_lab(lab_id: str) -> dict:
    response = await _proxy("POST", f"/labs/{lab_id}/reset")
    return response.json()


@router.delete("/{lab_id}", status_code=204)
async def delete_lab(lab_id: str) -> None:
    await _proxy("DELETE", f"/labs/{lab_id}")
