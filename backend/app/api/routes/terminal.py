import asyncio
import contextlib

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings

router = APIRouter(tags=["terminal"])


@router.websocket("/ws/terminal")
async def terminal_proxy(websocket: WebSocket) -> None:
    """Relays a browser WebSocket to the PTY WebSocket exposed by the Kali
    agent. The API never spawns a shell itself — it only forwards bytes
    between two WebSocket connections, keeping the shell confined to the
    isolated cyberlab-kali container.
    """
    await websocket.accept()
    settings = get_settings()
    kali_ws_base = settings.kali_agent_url.replace("http://", "ws://").replace("https://", "wss://")
    uri = f"{kali_ws_base}/terminal?token={settings.kali_agent_token}"

    try:
        async with websockets.connect(uri) as kali_ws:

            async def browser_to_kali() -> None:
                async for message in websocket.iter_text():
                    await kali_ws.send(message)

            async def kali_to_browser() -> None:
                async for message in kali_ws:
                    await websocket.send_text(message)

            browser_task = asyncio.create_task(browser_to_kali())
            kali_task = asyncio.create_task(kali_to_browser())
            _, pending = await asyncio.wait([browser_task, kali_task], return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except (WebSocketDisconnect, websockets.exceptions.ConnectionClosed):
        pass
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
