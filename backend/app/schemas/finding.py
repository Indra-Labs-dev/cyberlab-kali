import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.finding import Confidence, RiskPriority, Severity


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

    # Phase 15 -- materialized Risk Score cache (app/risk/service.py). NULL
    # until first computed (always computed at extraction time in practice,
    # see app/jobs/tasks.py::execute_job, so effectively never null for a
    # finding created since Phase 15 -- but never assume it, always check).
    cve_ids: list[str]
    cvss_score: float | None
    epss_score: float | None
    kev: bool | None
    risk_score: int | None
    risk_priority: RiskPriority | None
    risk_calculated_at: datetime | None
