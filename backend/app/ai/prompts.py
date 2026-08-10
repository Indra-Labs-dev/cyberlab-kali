import json


def build_tool_catalog_summary(tools: list[dict]) -> str:
    """Renders the AI-visible Tool Registry as a compact list for a system
    prompt, so the Assistant can answer "what tools can I use" questions
    grounded in what's actually registered -- never inventing a tool name.
    Only ai_allowed tools are ever passed in here by the caller.
    """
    lines = [f"- {t['name']} ({t['category']}): {t['description']}" for t in tools]
    return "\n".join(lines)


ANALYST_SYSTEM = """You are a defensive security analyst assistant inside CyberLab, a local \
cybersecurity lab tool used only for authorized testing (CTF, labs, pentest with permission, \
auditing systems the user owns). You analyze the output of a security tool that already ran \
and explain what it means — you never suggest or imply attacking systems without authorization.

Respond with a single JSON object matching exactly this shape, no prose outside the JSON:
{
  "risk": "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "summary": "one or two sentence plain-language summary",
  "findings": ["short finding 1", "short finding 2", ...],
  "recommendations": ["short recommendation 1", ...],
  "next_steps": ["short suggested next step 1", ...]
}
If the tool found nothing notable, use risk "INFO" and say so in the summary."""


def build_analysis_prompt(tool: str, target: str, exit_code: int | None, parsed_result: dict, stdout: str) -> str:
    truncated_stdout = stdout[:4000]
    return (
        f"Tool: {tool}\n"
        f"Target: {target}\n"
        f"Exit code: {exit_code}\n"
        f"Parsed result (JSON):\n{json.dumps(parsed_result, indent=2)[:4000]}\n\n"
        f"Raw output (may be truncated):\n{truncated_stdout}\n"
    )


PLANNER_SYSTEM = """You are a mission planning assistant inside CyberLab, a local cybersecurity \
lab tool used only for authorized testing (CTF, labs, pentest with permission, auditing systems \
the user owns). Given a target and a goal, propose an ordered plan of reconnaissance/scanning \
steps using ONLY the tools listed below — never invent a tool that isn't listed. Prefer picking \
one of a tool's listed profiles (curated argument presets) over inventing raw options — only use \
"options" when no profile fits. You propose a plan for the user to review; you do not execute \
anything yourself.

Respond with a single JSON object matching exactly this shape, no prose outside the JSON:
{
  "steps": [
    {"label": "short step description", "tool": "<one of the listed tool names, or null for a \
manual/non-tool step>", "profile": "<one of that tool's listed profile names, or null>", \
"target": "<target to use>", "options": {<tool-specific options, only if profile is null>}, \
"rationale": "why this step, one sentence"}
  ]
}
Keep the plan to at most 6 steps, ordered from broad recon to more specific checks."""


def build_planner_prompt(
    target: str, goal: str, available_tools: list[dict], authorization_status: str | None = None
) -> str:
    tools_desc = json.dumps(
        [
            {
                "name": t["name"],
                "description": t["description"],
                "arguments": [a["name"] for a in t["arguments"]],
                "profiles": [{"name": p["name"], "description": p["description"]} for p in t["profiles"]],
            }
            for t in available_tools
        ],
        indent=2,
    )
    authorization_line = ""
    if authorization_status is not None:
        authorization_line = f"Target authorization status: {authorization_status}\n"
    return f"Target: {target}\n{authorization_line}Goal: {goal}\n\nAvailable tools:\n{tools_desc}\n"
