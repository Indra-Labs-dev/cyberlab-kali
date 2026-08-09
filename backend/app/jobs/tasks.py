from app.jobs.kali_client import run_tool
from app.tools import registry
from app.tools.parsers import parse_output


def run_tool_job(tool: str, args: list[str], timeout: int = 60) -> dict:
    """Executed by the RQ worker; delegates raw execution to the Kali agent."""
    return run_tool(tool, args, timeout=timeout)


def run_registered_tool_job(tool_name: str, params: dict, timeout: int | None = None) -> dict:
    """Executed by the RQ worker: validates `params` against the Tool Registry
    definition for `tool_name`, runs it via the Kali agent, and parses stdout
    into a normalized result.
    """
    tool = registry.get_tool(tool_name)
    args = registry.build_command(tool_name, params)
    effective_timeout = min(timeout or tool.default_timeout, tool.max_timeout)

    raw = run_tool(tool_name, args, timeout=effective_timeout)
    raw["parsed"] = parse_output(tool.output.parser, raw.get("stdout", ""))
    return raw
