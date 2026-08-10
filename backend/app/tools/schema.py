from typing import Literal

from pydantic import BaseModel, Field

ArgumentType = Literal["target", "url", "string", "boolean", "choice", "integer"]

# SAFE: passive/read-only, unlikely to disrupt a target (e.g. banner grabbing).
# CAUTION: active probing that's usually fine against lab/owned targets but
#   can be noisy or trigger IDS/alerting (e.g. port scanning).
# RESTRICTED: sends many requests / can stress or crash fragile services
#   (e.g. active vulnerability scanning) -- use with more care even in a lab.
RiskLevel = Literal["SAFE", "CAUTION", "RESTRICTED"]


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
    parser: str


class ToolDefinition(BaseModel):
    name: str
    category: str
    description: str = ""
    risk_level: RiskLevel = "CAUTION"
    command: CommandDef
    fixed_args: list[str] = Field(default_factory=list)
    arguments: list[ArgumentDef] = Field(default_factory=list)
    output: OutputDef
    default_timeout: int = 60
    max_timeout: int = 300
