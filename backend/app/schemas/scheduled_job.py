import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.scheduled_job import MIN_INTERVAL_SECONDS, ScheduledJobStatus


class ScheduledJobCreateRequest(BaseModel):
    tool: str
    profile: str | None = None
    params: dict = Field(default_factory=dict)
    interval_seconds: int

    @field_validator("interval_seconds")
    @classmethod
    def _min_interval(cls, value: int) -> int:
        if value < MIN_INTERVAL_SECONDS:
            raise ValueError(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}")
        return value


class ScheduledJobUpdateRequest(BaseModel):
    profile: str | None = None
    params: dict | None = None
    interval_seconds: int | None = None
    # PAUSED <-> ACTIVE via this field (human-driven, see PATCH
    # /api/schedules/{id}); DISABLED is otherwise only ever set by the
    # system (asset deleted, see app/scheduling/service.py) but a human can
    # still explicitly disable a schedule this way if desired.
    status: ScheduledJobStatus | None = None

    @field_validator("interval_seconds")
    @classmethod
    def _min_interval(cls, value: int | None) -> int | None:
        if value is not None and value < MIN_INTERVAL_SECONDS:
            raise ValueError(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}")
        return value


class ScheduledJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    asset_id: uuid.UUID | None
    tool: str
    profile: str | None
    params: dict
    interval_seconds: int
    status: ScheduledJobStatus
    next_run_at: datetime
    last_run_at: datetime | None
    last_job_id: uuid.UUID | None
    consecutive_failures: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
