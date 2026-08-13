import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.project import ProjectStatus


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    notes: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    notes: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class ProjectSummary(ProjectResponse):
    """Project response enriched with rollup counts for list views, so the
    frontend never has to fetch every related collection just to render a
    project card.
    """

    target_count: int = 0
    job_count: int = 0
    finding_count: int = 0
    lab_count: int = 0
