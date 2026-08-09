from app.jobs.kali_client import run_tool


def run_tool_job(tool: str, args: list[str], timeout: int = 60) -> dict:
    """Executed by the RQ worker inside cyberlab-worker; delegates to the Kali agent."""
    return run_tool(tool, args, timeout=timeout)
