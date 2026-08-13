import uuid
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
    # Name of a Tool Registry profile for `tool`, if the model picked one --
    # revalidated against the tool's actual profiles in planner.py the same
    # way `tool` itself is revalidated against the registry (never trusted
    # as-is). Falls back to None (raw `options`) if invalid.
    profile: str | None = None
    target: str | None = None
    # Set server-side (never by the model) when the plan was requested against
    # a registered Target -- lets the frontend run a step via POST /api/jobs
    # with target_id, so the same authorization enforcement as everywhere
    # else applies. Never derived from anything the AI outputs.
    target_id: uuid.UUID | None = None
    options: dict = Field(default_factory=dict)
    rationale: str = ""


class MissionPlan(BaseModel):
    goal: str
    target: str
    target_id: uuid.UUID | None = None
    steps: list[MissionStep] = Field(default_factory=list)
    raw_response: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    reply: str


class CorrelationSuggestion(BaseModel):
    """Phase 18 -- one proposed link between two existing Findings, from
    CorrelationAgent (app/ai/agents/correlation.py). Never a FindingRelation
    itself -- the calling route (app/api/routes/ai.py) is the only place
    that ever persists these, as a separate AICorrelationSuggestion row
    with status=PENDING, and finding_id/related_finding_id are revalidated
    against the real, already-loaded Finding set before that -- the agent
    never gets to invent an id that turns into a DB write on its own.
    """

    finding_id: uuid.UUID
    related_finding_id: uuid.UUID
    rationale: str = ""


class ReportProposal(BaseModel):
    """Phase 18 -- ReportAgent's (app/ai/agents/report.py) output: a
    structured proposal for a human to review and edit, never a report
    itself. The mandatory pattern is ReportAgent -> proposal -> human
    validation -> POST /api/reports -> real generation
    (app/api/routes/reports.py, completely untouched by this phase) --
    this schema only carries the proposal, it has no rendering capability.
    """

    title: str
    job_ids: list[uuid.UUID] = Field(default_factory=list)
    rationale: str = ""
