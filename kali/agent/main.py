import os
import re
import shutil
import subprocess
import time
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
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
