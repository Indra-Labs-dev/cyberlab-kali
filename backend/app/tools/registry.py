import logging
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml

from app.core.config import get_settings
from app.tools.schema import ArgumentDef, ToolDefinition

logger = logging.getLogger("cyberlab.tools.registry")

DEFINITIONS_DIR = Path(__file__).parent / "definitions"

# Same intent as kali/agent/main.py's UNSAFE_CHARS: subprocess is always called
# with shell=False, but rejecting shell metacharacters here gives a clear 4xx
# at the API boundary instead of relying solely on the agent's defense-in-depth check.
UNSAFE_CHARS = re.compile(r"[;&|`$<>\n\r\\]")

# Permissive hostname / IPv4 / IPv4-CIDR / IPv6-ish matcher. Its job is not to be
# a fully correct target validator (nmap will reject a malformed target on its
# own) — it exists to guarantee a target can never be mistaken for a flag
# (reject anything starting with '-') or smuggle shell metacharacters.
TARGET_PATTERN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-:]{0,251}[A-Za-z0-9])?(/[0-9]{1,3})?$")

STRING_ARG_PATTERN = re.compile(r"^[A-Za-z0-9.\-:_,/]{1,256}$")


class ToolNotFoundError(LookupError):
    pass


class ToolValidationError(ValueError):
    pass


def _validate_definition_integrity(tool: ToolDefinition) -> None:
    positional_count = 0
    target_arg_names = set()
    for arg in tool.arguments:
        if arg.positional:
            positional_count += 1
            # The first positional argument is where the job's resolved
            # target (target_id -> Target.address, or free-text `target`)
            # always lands (see app/api/routes/jobs.py). It's usually a
            # 'target'/'url', but a handful of tools (searchsploit) don't
            # scan a network address at all -- their "target" is a local
            # keyword, so a plain 'string' is allowed too. A second
            # positional slot exists for tools whose CLI takes a second bare
            # value after that (e.g. `nc host port`).
            if positional_count == 1 and arg.type not in ("target", "url", "string"):
                raise ValueError(
                    f"{tool.name}: the first positional argument {arg.name!r} must be 'target', 'url', or 'string'"
                )
        elif not arg.flag:
            raise ValueError(f"{tool.name}: non-positional argument {arg.name!r} must define a flag")
        if arg.type == "choice" and not arg.choices:
            raise ValueError(f"{tool.name}: choice argument {arg.name!r} must define choices")
        if arg.type in ("target", "url"):
            target_arg_names.add(arg.name)
    if positional_count > 2:
        raise ValueError(f"{tool.name}: at most two positional arguments are supported")

    known_arg_names = {arg.name for arg in tool.arguments}
    seen_profile_names = set()
    for profile in tool.profiles:
        if profile.name in seen_profile_names:
            raise ValueError(f"{tool.name}: duplicate profile name {profile.name!r}")
        seen_profile_names.add(profile.name)
        unknown = set(profile.args) - known_arg_names
        if unknown:
            raise ValueError(f"{tool.name}/{profile.name}: profile references unknown argument(s) {sorted(unknown)}")
        target_override = target_arg_names & set(profile.args)
        if target_override:
            raise ValueError(
                f"{tool.name}/{profile.name}: profile must not preset the target argument {sorted(target_override)}"
                " -- target always comes from the job/target_id, never a profile"
            )


def _load_one(path: Path) -> ToolDefinition:
    raw = yaml.safe_load(path.read_text())
    tool = ToolDefinition.model_validate(raw)
    _validate_definition_integrity(tool)
    return tool


@lru_cache
def _load_definitions() -> dict[str, ToolDefinition]:
    definitions: dict[str, ToolDefinition] = {}
    # Built-in, repo-committed definitions -- a bad file here is a real bug
    # (never shipped without being tested), so it fails loudly and takes
    # down the registry, exactly as before Plugin System existed.
    for path in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        tool = _load_one(path)
        definitions[tool.name] = tool

    # Plugin System (roadmap §8) -- see Settings.tool_definitions_extra_dir.
    # Unlike the loop above, a malformed file here is isolated (logged,
    # skipped) rather than crashing the whole registry: these files are
    # operator-authored and inherently more error-prone, and one typo must
    # never take the 31 curated tools down with it. A name collision with
    # a built-in tool is rejected loudly rather than silently shadowing
    # curated behavior -- an operator renames their file, the curated tool
    # is never at risk of being overridden by mistake.
    extra_dir = get_settings().tool_definitions_extra_dir
    if extra_dir:
        for path in sorted(Path(extra_dir).glob("*.yaml")):
            try:
                tool = _load_one(path)
            except Exception:
                logger.exception("plugin tool definition failed to load, skipped: %s", path)
                continue
            if tool.name in definitions:
                logger.error(
                    "plugin tool definition %s declares name %r, which collides with a built-in tool -- skipped",
                    path,
                    tool.name,
                )
                continue
            definitions[tool.name] = tool
    return definitions


def list_tools() -> list[ToolDefinition]:
    return list(_load_definitions().values())


def get_tool(name: str) -> ToolDefinition:
    try:
        return _load_definitions()[name]
    except KeyError as exc:
        raise ToolNotFoundError(f"unknown or disallowed tool: {name}") from exc


def get_profile(tool: ToolDefinition, profile_name: str):
    for profile in tool.profiles:
        if profile.name == profile_name:
            return profile
    raise ToolValidationError(f"unknown profile {profile_name!r} for tool {tool.name!r}")


def effective_timeout(tool: ToolDefinition, profile: str | None, requested_timeout: int | None) -> int:
    base = tool.default_timeout
    if profile is not None:
        profile_def = get_profile(tool, profile)
        if profile_def.timeout is not None:
            base = profile_def.timeout
    return min(requested_timeout or base, tool.max_timeout)


def _validate_target(arg: ArgumentDef, value: str) -> str:
    if not isinstance(value, str) or not TARGET_PATTERN.match(value):
        raise ToolValidationError(f"invalid target for argument {arg.name!r}: {value!r}")
    return value


def _validate_url(arg: ArgumentDef, value: str) -> str:
    if not isinstance(value, str) or not value or UNSAFE_CHARS.search(value) or value.startswith("-"):
        raise ToolValidationError(f"invalid URL for argument {arg.name!r}: {value!r}")

    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme not in ("http", "https", "ldap", "ldaps"):
            raise ToolValidationError(f"argument {arg.name!r} must use http, https, ldap, or ldaps: {value!r}")
        host = parsed.hostname or ""
        if not host or not TARGET_PATTERN.match(host):
            raise ToolValidationError(f"argument {arg.name!r} has an invalid host: {value!r}")
    elif not TARGET_PATTERN.match(value):
        raise ToolValidationError(f"invalid target for argument {arg.name!r}: {value!r}")

    return value


def _validate_string(arg: ArgumentDef, value: str) -> str:
    if not isinstance(value, str):
        raise ToolValidationError(f"argument {arg.name!r} must be a string")
    if UNSAFE_CHARS.search(value):
        raise ToolValidationError(f"argument {arg.name!r} contains unsafe characters")
    pattern = re.compile(arg.pattern) if arg.pattern else STRING_ARG_PATTERN
    if not pattern.match(value):
        raise ToolValidationError(f"argument {arg.name!r} does not match the expected format: {value!r}")
    return value


def _validate_choice(arg: ArgumentDef, value: str) -> str:
    if value not in (arg.choices or []):
        raise ToolValidationError(f"argument {arg.name!r} must be one of {arg.choices}, got {value!r}")
    return value


def _validate_integer(arg: ArgumentDef, value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ToolValidationError(f"argument {arg.name!r} must be an integer")
    if arg.min_value is not None and value < arg.min_value:
        raise ToolValidationError(f"argument {arg.name!r} must be >= {arg.min_value}")
    if arg.max_value is not None and value > arg.max_value:
        raise ToolValidationError(f"argument {arg.name!r} must be <= {arg.max_value}")
    return value


def build_command(tool_name: str, params: dict, profile: str | None = None) -> list[str]:
    """Validate `params` against the tool's definition and return the argument
    list to send to the Kali agent (the executable itself is resolved there).

    `profile`, if given, supplies default argument values (a curated preset)
    that `params` may override key-by-key -- it is a starting point, not a
    separate trust boundary. Every value, whether it came from the profile
    or from `params`, goes through the exact same per-argument validation
    below; a profile can never smuggle in something build_command wouldn't
    otherwise accept.
    """
    tool = get_tool(tool_name)
    args: list[str] = list(tool.fixed_args)
    positional: list[str] = []

    effective_params = dict(params)
    if profile is not None:
        profile_def = get_profile(tool, profile)
        effective_params = {**profile_def.args, **params}
    params = effective_params

    known_names = {arg.name for arg in tool.arguments}
    unknown = set(params) - known_names
    if unknown:
        raise ToolValidationError(f"unknown argument(s) for {tool_name}: {sorted(unknown)}")

    for arg in tool.arguments:
        value = params.get(arg.name, arg.default)
        if value is None:
            if arg.required:
                raise ToolValidationError(f"missing required argument: {arg.name}")
            continue

        if arg.type == "target":
            value = _validate_target(arg, value)
            if arg.positional:
                positional.append(value)
            else:
                args += [arg.flag, value]
        elif arg.type == "url":
            value = _validate_url(arg, value)
            if arg.positional:
                positional.append(value)
            else:
                args += [arg.flag, value]
        elif arg.type == "string":
            value = _validate_string(arg, value)
            if arg.positional:
                positional.append(value)
            else:
                args += [arg.flag, value]
        elif arg.type == "boolean":
            if not isinstance(value, bool):
                raise ToolValidationError(f"argument {arg.name!r} must be a boolean")
            if value:
                args.append(arg.flag)
        elif arg.type == "choice":
            value = _validate_choice(arg, value)
            args += [arg.flag, value]
        elif arg.type == "integer":
            value = _validate_integer(arg, value)
            if arg.positional:
                positional.append(str(value))
            else:
                args += [arg.flag, str(value)]

    return args + positional
