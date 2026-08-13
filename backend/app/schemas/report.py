import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.report import ReportFormat, ReportTemplate


class ReportCreateRequest(BaseModel):
    title: str
    job_ids: list[uuid.UUID]
    format: ReportFormat
    template: ReportTemplate = ReportTemplate.TECHNICAL


class ReportMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    format: ReportFormat
    template: ReportTemplate
    job_ids: list
    created_at: datetime
