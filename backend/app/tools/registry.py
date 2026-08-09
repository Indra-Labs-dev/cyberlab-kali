import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml

from app.tools.schema import ArgumentDef, ToolDefinition

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
    for arg in tool.arguments:
        if arg.positional:
            positional_count += 1
            if arg.type not in ("target", "url"):
                raise ValueError(f"{tool.name}: positional argument {arg.name!r} must be of type 'target' or 'url'")
        elif not arg.flag:
            raise ValueError(f"{tool.name}: non-positional argument {arg.name!r} must define a flag")
        if arg.type == "choice" and not arg.choices:
            raise ValueError(f"{tool.name}: choice argument {arg.name!r} must define choices")
    if positional_count > 1:
        raise ValueError(f"{tool.name}: at most one positional argument is supported")


@lru_cache
def _load_definitions() -> dict[str, ToolDefinition]:
    definitions: dict[str, ToolDefinition] = {}
    for path in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        tool = ToolDefinition.model_validate(raw)
        _validate_definition_integrity(tool)
        definitions[tool.name] = tool
    return definitions


def list_tools() -> list[ToolDefinition]:
    return list(_load_definitions().values())


def get_tool(name: str) -> ToolDefinition:
    try:
        return _load_definitions()[name]
    except KeyError as exc:
        raise ToolNotFoundError(f"unknown or disallowed tool: {name}") from exc


def _validate_target(arg: ArgumentDef, value: str) -> str:
    if not isinstance(value, str) or not TARGET_PATTERN.match(value):
        raise ToolValidationError(f"invalid target for argument {arg.name!r}: {value!r}")
    return value


def _validate_url(arg: ArgumentDef, value: str) -> str:
    if not isinstance(value, str) or not value or UNSAFE_CHARS.search(value) or value.startswith("-"):
        raise ToolValidationError(f"invalid URL for argument {arg.name!r}: {value!r}")

    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme not in ("http", "https"):
            raise ToolValidationError(f"argument {arg.name!r} must use http or https: {value!r}")
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


def build_command(tool_name: str, params: dict) -> list[str]:
    """Validate `params` against the tool's definition and return the argument
    list to send to the Kali agent (the executable itself is resolved there).
    """
    tool = get_tool(tool_name)
    args: list[str] = list(tool.fixed_args)
    positional: list[str] = []

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
            args += [arg.flag, str(value)]

    return args + positional
