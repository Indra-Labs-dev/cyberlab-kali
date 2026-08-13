import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.job import JobStatus


class JobCreateRequest(BaseModel):
    tool: str
    # Either target (free-text, quick ad-hoc scans) or target_id (a
    # registered Target, subject to authorization enforcement) must be set.
    # When target_id is given, the actual scan address is resolved from the
    # Target record server-side -- `target` here is ignored if both are sent.
    target: str | None = None
    target_id: uuid.UUID | None = None
    # A named Tool Registry profile (e.g. "quick_scan") to use as the default
    # argument set -- `options` may still override individual keys. Purely a
    # convenience/UI layer: build_command() validates the resulting arguments
    # identically whether they came from a profile or were typed manually.
    profile: str | None = None
    options: dict = Field(default_factory=dict)
    timeout: int | None = None

    @model_validator(mode="after")
    def _require_target_or_target_id(self) -> "JobCreateRequest":
        if not self.target and not self.target_id:
            raise ValueError("either target or target_id is required")
        return self


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool: str
    profile: str | None
    target: str
    project_id: uuid.UUID | None
    target_id: uuid.UUID | None
    params: dict
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    result: dict | None
    error: str | None
    ai_analysis: dict | None
    evidence_sha256: str | None
