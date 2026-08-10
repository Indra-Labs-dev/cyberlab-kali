import asyncio
import fcntl
import json
import os
import pty
import re
import shutil
import struct
import subprocess
import termios
import time
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

app = FastAPI(title="CyberLab Kali Agent")

AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "")

# Allowlist: logical tool name -> resolved absolute executable path.
# Resolved once at startup so a request can never redirect execution to another binary.
ALLOWED_TOOLS: dict[str, str] = {}
for _tool in ("nmap", "whatweb", "nikto"):
    _path = shutil.which(_tool)
    if _path:
        ALLOWED_TOOLS[_tool] = _path

MAX_TIMEOUT_SECONDS = 300
MAX_ARGS = 32
MAX_ARG_LENGTH = 256

# Rejects shell metacharacters even though subprocess is called without a shell,
# as defense in depth and to keep arguments predictable.
UNSAFE_CHARS = re.compile(r"[;&|`$<>\n\r\\]")


class ExecRequest(BaseModel):
    tool: Literal["nmap", "whatweb", "nikto"]
    args: list[str] = Field(default_factory=list, max_length=MAX_ARGS)
    timeout: int = Field(default=60, ge=1, le=MAX_TIMEOUT_SECONDS)


class ExecResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


def _validate_args(args: list[str]) -> None:
    for arg in args:
        if not arg or len(arg) > MAX_ARG_LENGTH:
            raise HTTPException(status_code=400, detail=f"invalid argument length: {arg!r}")
        if UNSAFE_CHARS.search(arg):
            raise HTTPException(status_code=400, detail=f"argument contains unsafe characters: {arg!r}")


def _require_auth(x_agent_token: str | None) -> None:
    if not AGENT_TOKEN or x_agent_token != AGENT_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing agent token")


SHELL = shutil.which("bash") or shutil.which("sh") or "/bin/sh"


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "tools_available": sorted(ALLOWED_TOOLS.keys())}


@app.post("/exec", response_model=ExecResponse)
async def exec_tool(request: ExecRequest, x_agent_token: str | None = Header(default=None)) -> ExecResponse:
    _require_auth(x_agent_token)

    executable = ALLOWED_TOOLS.get(request.tool)
    if executable is None:
        raise HTTPException(status_code=400, detail=f"tool not allowed or not installed: {request.tool}")

    _validate_args(request.args)

    command = [executable, *request.args]
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=request.timeout,
            shell=False,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\n[cyberlab] process killed after timeout"
    duration_ms = int((time.monotonic() - started) * 1000)

    return ExecResponse(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


@app.websocket("/terminal")
async def terminal_ws(websocket: WebSocket, token: str = Query(default="")) -> None:
    if not AGENT_TOKEN or token != AGENT_TOKEN:
        await websocket.close(code=4401)
        return
    await websocket.accept()

    master_fd, slave_fd = pty.openpty()
    _set_winsize(master_fd, 24, 80)
    proc = subprocess.Popen(
        [SHELL],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=os.setsid,
        cwd=os.path.expanduser("~"),
        env={**os.environ, "TERM": "xterm-256color"},
    )
    os.close(slave_fd)

    loop = asyncio.get_event_loop()
    output_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def on_readable() -> None:
        try:
            data = os.read(master_fd, 4096)
        except OSError:
            data = b""
        output_queue.put_nowait(data or None)

    loop.add_reader(master_fd, on_readable)

    async def pty_to_ws() -> None:
        while True:
            data = await output_queue.get()
            if data is None:
                break
            await websocket.send_text(json.dumps({"type": "stdout", "data": data.decode(errors="replace")}))

    async def ws_to_pty() -> None:
        while True:
            text = await websocket.receive_text()
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if message.get("type") == "stdin":
                os.write(master_fd, message.get("data", "").encode())
            elif message.get("type") == "resize":
                _set_winsize(master_fd, int(message.get("rows", 24)), int(message.get("cols", 80)))

    try:
        await asyncio.gather(pty_to_ws(), ws_to_pty())
    except WebSocketDisconnect:
        pass
    finally:
        loop.remove_reader(master_fd)
        try:
            os.close(master_fd)
        except OSError:
            pass
        proc.terminate()
        # Reap the child so it doesn't linger as a zombie — terminate() alone
        # only sends SIGTERM, it doesn't wait for the process table entry to clear.
        await loop.run_in_executor(None, proc.wait)
