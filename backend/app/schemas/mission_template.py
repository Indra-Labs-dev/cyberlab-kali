import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.mission_template import ChainConditionType, ChainRunStatus, ChainRunStepStatus
from app.tools import registry

# Sanity bound only -- a human authors a template once, ahead of time,
# there is no AI proposing an unbounded plan the way Phase 18's Mission
# has to guard against. Just defense in depth against a runaway template.
_MAX_TEMPLATE_STEPS = 20


class MissionTemplateStepCreateRequest(BaseModel):
    tool: str
    profile: str | None = None
    options: dict = Field(default_factory=dict)
    condition_type: ChainConditionType = ChainConditionType.ALWAYS
    condition_params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _tool_and_profile_must_be_registered(self) -> "MissionTemplateStepCreateRequest":
        try:
            tool_def = registry.get_tool(self.tool)
        except registry.ToolNotFoundError as exc:
            raise ValueError(str(exc)) from exc
        if self.profile is not None:
            try:
                registry.get_profile(tool_def, self.profile)
            except registry.ToolValidationError as exc:
                raise ValueError(str(exc)) from exc
        return self


class MissionTemplateCreateRequest(BaseModel):
    name: str
    description: str | None = None
    steps: list[MissionTemplateStepCreateRequest]

    @model_validator(mode="after")
    def _steps_are_well_formed(self) -> "MissionTemplateCreateRequest":
        if not self.steps:
            raise ValueError("a template needs at least one step")
        if len(self.steps) > _MAX_TEMPLATE_STEPS:
            raise ValueError(f"a template can have at most {_MAX_TEMPLATE_STEPS} steps")
        if self.steps[0].condition_type != ChainConditionType.ALWAYS:
            raise ValueError("the first step has no previous step to gate on -- its condition_type must be ALWAYS")
        return self


class MissionTemplateStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_order: int
    tool: str
    profile: str | None
    options: dict
    condition_type: ChainConditionType
    condition_params: dict


class MissionTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    steps: list[MissionTemplateStepResponse] = Field(default_factory=list)


class ChainRunCreateRequest(BaseModel):
    template_id: uuid.UUID
    target_id: uuid.UUID


class ChainRunStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_order: int
    tool: str
    profile: str | None
    options: dict
    condition_type: ChainConditionType
    condition_params: dict
    status: ChainRunStepStatus
    job_id: uuid.UUID | None
    skip_reason: str | None
    created_at: datetime


class ChainRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID | None
    target_id: uuid.UUID
    project_id: uuid.UUID | None
    status: ChainRunStatus
    created_at: datetime
    finished_at: datetime | None
    steps: list[ChainRunStepResponse] = Field(default_factory=list)
