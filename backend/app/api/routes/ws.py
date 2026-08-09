import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis as AsyncRedis

from app.core.config import get_settings
from app.jobs.pubsub import channel_for_job

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/jobs/{job_id}")
async def job_updates_ws(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    settings = get_settings()
    redis = AsyncRedis.from_url(settings.redis_url)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel_for_job(job_id))

    async def forward_updates() -> None:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            await websocket.send_text(data if isinstance(data, str) else data.decode())

    async def watch_disconnect() -> None:
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                await websocket.receive_text()

    forward_task = asyncio.create_task(forward_updates())
    disconnect_task = asyncio.create_task(watch_disconnect())
    try:
        await asyncio.wait([forward_task, disconnect_task], return_when=asyncio.FIRST_COMPLETED)
    finally:
        forward_task.cancel()
        disconnect_task.cancel()
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel_for_job(job_id))
            await pubsub.close()
        await redis.close()
