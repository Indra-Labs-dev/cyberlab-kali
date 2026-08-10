import asyncio
import os
from functools import partial
from typing import TypeVar

from docker.errors import APIError
from fastapi import FastAPI, Header, HTTPException

import docker_manager
import registry
from schema import LabDefinition, LabInstance

app = FastAPI(title="CyberLab Lab Manager")

AGENT_TOKEN = os.environ.get("LABMANAGER_TOKEN", "")

T = TypeVar("T")


async def _run_blocking(func, *args, **kwargs) -> T:
    """The docker SDK is synchronous; running it directly inside an async
    route handler would block the event loop for as long as the call takes —
    including an image pull, which can take minutes on first run. Offloading
    to a thread keeps /health and other requests responsive meanwhile.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def _require_auth(x_agent_token: str | None) -> None:
    if not AGENT_TOKEN or x_agent_token != AGENT_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing agent token")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/definitions", response_model=list[LabDefinition])
async def list_definitions(x_agent_token: str | None = Header(default=None)) -> list[LabDefinition]:
    _require_auth(x_agent_token)
    return registry.list_definitions()


@app.get("/labs", response_model=list[LabInstance])
async def list_labs(x_agent_token: str | None = Header(default=None)) -> list[LabInstance]:
    _require_auth(x_agent_token)
    return await _run_blocking(docker_manager.list_labs)


@app.post("/labs", response_model=LabInstance, status_code=201)
async def create_lab(definition: str, x_agent_token: str | None = Header(default=None)) -> LabInstance:
    _require_auth(x_agent_token)
    try:
        return await _run_blocking(docker_manager.create_lab, definition)
    except registry.LabDefinitionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"docker error: {exc}") from exc


@app.get("/labs/{lab_id}", response_model=LabInstance)
async def get_lab(lab_id: str, x_agent_token: str | None = Header(default=None)) -> LabInstance:
    _require_auth(x_agent_token)
    try:
        return await _run_blocking(docker_manager.get_lab, lab_id)
    except docker_manager.LabNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/labs/{lab_id}/start", response_model=LabInstance)
async def start_lab(lab_id: str, x_agent_token: str | None = Header(default=None)) -> LabInstance:
    _require_auth(x_agent_token)
    try:
        return await _run_blocking(docker_manager.start_lab, lab_id)
    except docker_manager.LabNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/labs/{lab_id}/stop", response_model=LabInstance)
async def stop_lab(lab_id: str, x_agent_token: str | None = Header(default=None)) -> LabInstance:
    _require_auth(x_agent_token)
    try:
        return await _run_blocking(docker_manager.stop_lab, lab_id)
    except docker_manager.LabNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/labs/{lab_id}/reset", response_model=LabInstance)
async def reset_lab(lab_id: str, x_agent_token: str | None = Header(default=None)) -> LabInstance:
    _require_auth(x_agent_token)
    try:
        return await _run_blocking(docker_manager.reset_lab, lab_id)
    except docker_manager.LabNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/labs/{lab_id}", status_code=204)
async def delete_lab(lab_id: str, x_agent_token: str | None = Header(default=None)) -> None:
    _require_auth(x_agent_token)
    try:
        await _run_blocking(docker_manager.delete_lab, lab_id)
    except docker_manager.LabNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
