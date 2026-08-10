import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.finding import Confidence, Severity


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    target: str
    source_tool: str
    title: str
    description: str
    severity: Severity
    confidence: Confidence
    evidence: dict
    recommendation: str | None
    created_at: datetime
