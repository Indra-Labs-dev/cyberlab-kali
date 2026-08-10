from typing import Literal

from pydantic import BaseModel, Field, model_validator

ArgumentType = Literal["target", "url", "string", "boolean", "choice", "integer"]

# SAFE: passive/read-only, unlikely to disrupt a target (e.g. banner grabbing).
# CAUTION: active probing that's usually fine against lab/owned targets but
#   can be noisy or trigger IDS/alerting (e.g. port scanning).
# RESTRICTED: sends many requests / can stress or crash fragile services
#   (e.g. active vulnerability scanning) -- use with more care even in a lab.
# MANUAL_ONLY: intrusive enough (data exfiltration/modification, credential
#   attacks) that it must never be reachable through the AI, even proposed --
#   always implies ai_allowed=False (enforced in ToolDefinition below). Still
#   runnable by a human directly via the Tools page; "manual" means "AI can't
#   touch it", not "nobody can run it".
RiskLevel = Literal["SAFE", "CAUTION", "RESTRICTED", "MANUAL_ONLY"]


class ArgumentDef(BaseModel):
    name: str
    type: ArgumentType
    required: bool = False
    positional: bool = False
    flag: str | None = None
    default: bool | str | int | None = None
    pattern: str | None = None
    choices: list[str] | None = None
    min_value: int | None = None
    max_value: int | None = None
    description: str = ""


class CommandDef(BaseModel):
    executable: str


class OutputDef(BaseModel):
    format: Literal["xml", "json", "text"]
    # "none" is a valid, explicit value: the tool's stdout is shown as-is,
    # never claimed to be structured. See app/tools/parsers/__init__.py.
    parser: str


class ToolProfile(BaseModel):
    """A named, curated preset of argument values -- what the frontend and
    the AI planner actually offer, instead of raw CLI arguments. A profile
    never bypasses validation: its `args` are just a starting point that
    still goes through the same build_command() type/pattern checks as any
    manually-entered value.
    """

    name: str
    description: str = ""
    args: dict[str, bool | str | int] = Field(default_factory=dict)
    timeout: int | None = None
    # Overrides the tool's risk_level for this specific profile when a
    # profile is meaningfully more/less aggressive than the tool's default
    # (e.g. nmap's "Vulnerability NSE" profile vs. its "Quick Scan" profile).
    risk_level: RiskLevel | None = None
    # Informational hint for the frontend (which TargetType this profile
    # expects) -- not enforced, Target typing is already loose by design.
    target_type_hint: str | None = None


class ToolDefinition(BaseModel):
    name: str
    category: str
    description: str = ""
    risk_level: RiskLevel = "CAUTION"
    # Whether the AI Mission Planner may ever propose this tool. Enforced in
    # app/ai/planner.py the same way a hallucinated/unregistered tool name is
    # stripped -- never trusted from model output, always checked against
    # this field. A human can still run a non-AI-allowed tool directly via
    # the Tools page; this only gates the AI's reach.
    ai_allowed: bool = True
    command: CommandDef
    fixed_args: list[str] = Field(default_factory=list)
    arguments: list[ArgumentDef] = Field(default_factory=list)
    profiles: list[ToolProfile] = Field(default_factory=list)
    output: OutputDef
    default_timeout: int = 60
    max_timeout: int = 300

    @model_validator(mode="after")
    def _manual_only_implies_not_ai_allowed(self) -> "ToolDefinition":
        if self.risk_level == "MANUAL_ONLY" and self.ai_allowed:
            raise ValueError(f"{self.name}: risk_level MANUAL_ONLY requires ai_allowed: false")
        return self
