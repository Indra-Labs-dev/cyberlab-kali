import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.mission import MissionStatus, MissionStepStatus


class MissionCreateRequest(BaseModel):
    # Mandatory and always a real, registered Asset -- unlike JobCreateRequest,
    # a Mission never accepts free-text target: every step must be
    # re-checkable against is_executable() at execution time, which requires
    # a real Asset row (see app/ai/orchestrator.py).
    target_id: uuid.UUID
    goal: str
    max_steps: int = Field(default=10, gt=0, le=50)


class MissionStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_order: int
    label: str
    tool: str | None
    profile: str | None
    options: dict
    rationale: str
    status: MissionStepStatus
    job_id: uuid.UUID | None
    skip_reason: str | None
    created_at: datetime


class MissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    target_id: uuid.UUID
    goal: str
    status: MissionStatus
    max_steps: int
    created_at: datetime
    approved_at: datetime | None
    finished_at: datetime | None
    steps: list[MissionStepResponse] = Field(default_factory=list)
