import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus


class JobCreateRequest(BaseModel):
    tool: str
    target: str
    options: dict = Field(default_factory=dict)
    timeout: int | None = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool: str
    target: str
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
