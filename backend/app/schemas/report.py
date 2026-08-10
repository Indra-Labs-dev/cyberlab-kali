import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.report import ReportFormat


class ReportCreateRequest(BaseModel):
    title: str
    job_ids: list[uuid.UUID]
    format: ReportFormat


class ReportMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    format: ReportFormat
    job_ids: list
    created_at: datetime
