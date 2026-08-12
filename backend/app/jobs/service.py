"""Shared job-creation logic used by both `POST /api/jobs` (async route,
manual runs) and the Phase 14 scheduler ticker (sync, background thread in
the worker process) -- so a scheduled run goes through the exact same
Policy Engine validation as a manual one, not a parallel reimplementation.

The DB session mechanics differ (async for the API, sync for the worker,
the same split already established by app/jobs/tasks.py for job execution),
so this module holds only the pure, session-independent pieces: building
the tool's full argument dict and validating it against the Tool Registry.
Authorization (`app.targets.authorization.is_executable`) is already a pure
function of an already-loaded Asset object and is reused as-is by both
callers -- it never needed splitting.
"""

from dataclasses import dataclass

from app.tools import registry


@dataclass
class PreparedJob:
    full_params: dict
    effective_timeout: int


def prepare_job(
    tool_name: str,
    profile: str | None,
    options: dict,
    target_address: str,
    requested_timeout: int | None = None,
) -> PreparedJob:
    """Resolve a tool+profile+options+target into the validated argument dict
    and effective timeout that both job-creation paths persist onto the Job
    row and hand to the worker. Raises registry.ToolNotFoundError /
    registry.ToolValidationError exactly as `build_command` does -- callers
    translate those into their own error surface (HTTPException for the API,
    a recorded `last_error` for the scheduler).
    """
    tool_def = registry.get_tool(tool_name)

    profile_args: dict = {}
    if profile is not None:
        profile_args = registry.get_profile(tool_def, profile).args

    full_params = {**profile_args, **options, "target": target_address}
    registry.build_command(tool_name, full_params)

    effective_timeout = registry.effective_timeout(tool_def, profile, requested_timeout)
    return PreparedJob(full_params=full_params, effective_timeout=effective_timeout)
