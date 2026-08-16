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

# Allowlist: logical tool name -> resolved absolute executable path. Resolved
# once at startup so a request can never redirect execution to another
# binary, and so a tool that failed to install (missing from the image)
# simply never appears here rather than being trusted blindly. This list
# must be kept in lockstep with backend/app/tools/definitions/*.yaml on the
# API side -- see docs/tools.md for the full curated list and rationale.
# The *logical* name here is the registry tool name, which is not always the
# executable's own filename (e.g. "dnsutils_dig" -> "dig").
CANDIDATE_TOOLS: dict[str, str] = {
    # Reconnaissance
    "nmap": "nmap",
    "masscan": "masscan",
    "arp-scan": "arp-scan",
    "netdiscover": "netdiscover",
    # DNS / network
    "dig": "dig",
    "host": "host",
    "nslookup": "nslookup",
    "traceroute": "traceroute",
    "whois": "whois",
    "nc": "nc",
    # Web reconnaissance
    "whatweb": "whatweb",
    "wafw00f": "wafw00f",
    "gobuster": "gobuster",
    "ffuf": "ffuf",
    # Web security
    "nikto": "nikto",
    "nuclei": "nuclei",
    "sqlmap": "sqlmap",
    # SSL/TLS
    "sslscan": "sslscan",
    "testssl": "testssl",
    # Enumeration
    "enum4linux": "enum4linux",
    "smbclient": "smbclient",
    "rpcclient": "rpcclient",
    "ldapsearch": "ldapsearch",
    # Vulnerability / security analysis
    "searchsploit": "searchsploit",
    # OSINT
    "theharvester": "theHarvester",
    "amass": "amass",
    "subfinder": "subfinder",
    "dnsrecon": "dnsrecon",
    # Utilities
    "curl": "curl",
    "wget": "wget",
    "openssl": "openssl",
    # NOTE: lynis and jq are intentionally NOT in this list even though both
    # are installed in the image. Neither fits the Tool Registry's per-job,
    # single-target model: lynis audits whatever system it runs on (no
    # network target at all -- running it against a "target" would just
    # self-audit this container, which isn't a meaningful scan action), and
    # jq processes JSON via stdin (no target, and no inter-job piping exists
    # in this architecture). Both remain available for manual use via the
    # Terminal, which is unrestricted by design -- see docs/tools.md.
}

def _parse_extra_tools(raw: str, existing: dict[str, str]) -> dict[str, str]:
    """Plugin System (roadmap §8) -- an optional, operator-set second
    source of candidate tools, format "name1:executable1,name2:executable2".
    Empty input -> empty result, zero effect unless EXTRA_ALLOWED_TOOLS is
    explicitly set. Malformed entries (no colon, empty name/executable)
    are skipped individually, never raise -- one operator typo must not
    prevent the agent from starting. A name already present in `existing`
    (the curated CANDIDATE_TOOLS) is skipped too: a typo in
    EXTRA_ALLOWED_TOOLS must never be able to shadow a curated tool's
    already-resolved path. Every returned entry still goes through the
    exact same shutil.which() resolution as CANDIDATE_TOOLS below -- a
    name listed here still never becomes runnable unless the binary is
    genuinely present in this image (e.g. an operator's own Dockerfile
    extending cyberlab-kali). See docs/phase-plugin-system.md.
    """
    extra: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, executable = entry.partition(":")
        name, executable = name.strip(), executable.strip()
        if not sep or not name or not executable:
            continue
        if name in existing:
            continue
        extra[name] = executable
    return extra


EXTRA_CANDIDATE_TOOLS: dict[str, str] = _parse_extra_tools(os.environ.get("EXTRA_ALLOWED_TOOLS", ""), CANDIDATE_TOOLS)

ALLOWED_TOOLS: dict[str, str] = {}
for _name, _executable in {**CANDIDATE_TOOLS, **EXTRA_CANDIDATE_TOOLS}.items():
    _path = shutil.which(_executable)
    if _path:
        ALLOWED_TOOLS[_name] = _path

MAX_TIMEOUT_SECONDS = 300
MAX_ARGS = 32
MAX_ARG_LENGTH = 256

# Rejects shell metacharacters even though subprocess is called without a shell,
# as defense in depth and to keep arguments predictable.
UNSAFE_CHARS = re.compile(r"[;&|`$<>\n\r\\]")


class ExecRequest(BaseModel):
    # Not a Literal of fixed names anymore (the arsenal is too large to hand-
    # maintain as a type union) -- validated against ALLOWED_TOOLS below
    # instead, which has the exact same effect: an unresolved/unknown name
    # is rejected before any subprocess is ever considered.
    tool: str
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


TOOL_HEALTH_CHECK_TIMEOUT = 5


def _check_tool_health(name: str, executable: str) -> dict:
    """Non-destructive invocation check: never runs a real scan, just tries
    a version/help flag and confirms the binary actually produces output.
    Not every tool supports --version, so --help is tried as a fallback.
    """
    for probe in (["--version"], ["--help"]):
        try:
            result = subprocess.run(
                [executable, *probe],
                capture_output=True,
                text=True,
                timeout=TOOL_HEALTH_CHECK_TIMEOUT,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            continue
        except OSError:
            return {"name": name, "status": "broken", "detail": "failed to execute"}
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if output:
            return {"name": name, "status": "ready", "detail": output.splitlines()[0][:200]}
    return {"name": name, "status": "broken", "detail": "no output from --version or --help"}


@app.get("/health/tools")
async def health_tools(x_agent_token: str | None = Header(default=None)) -> list[dict]:
    _require_auth(x_agent_token)
    loop = asyncio.get_event_loop()
    checks = [loop.run_in_executor(None, _check_tool_health, name, path) for name, path in ALLOWED_TOOLS.items()]
    return list(await asyncio.gather(*checks))


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
        # exc.stdout/.stderr are documented as str when text=True is passed
        # to subprocess.run, but in practice CPython can still hand back
        # bytes here for output captured right as the process is killed
        # (the decode happens in communicate(), not before) -- found via
        # Phase 12 end-to-end testing (nikto timing out on a slow target
        # crashed this handler with "can't concat str to bytes"). Coerce
        # defensively rather than trust the type the stdlib claims.
        def _to_text(value: str | bytes | None) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode(errors="replace")
            return value

        timed_out = True
        exit_code = -1
        stdout = _to_text(exc.stdout)
        stderr = _to_text(exc.stderr) + "\n[cyberlab] process killed after timeout"
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
