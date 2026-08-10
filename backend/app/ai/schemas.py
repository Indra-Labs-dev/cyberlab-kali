from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


class AnalysisResult(BaseModel):
    risk: RiskLevel = "INFO"
    summary: str = ""
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    raw_response: str | None = None  # populated only if structured parsing failed


class MissionStep(BaseModel):
    label: str
    tool: str | None = None
    target: str | None = None
    options: dict = Field(default_factory=dict)
    rationale: str = ""


class MissionPlan(BaseModel):
    goal: str
    target: str
    steps: list[MissionStep] = Field(default_factory=list)
    raw_response: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    reply: str
