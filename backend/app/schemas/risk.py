import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.asset import AssetCriticality
from app.models.finding import Confidence, RiskPriority, Severity


class RiskInputsResponse(BaseModel):
    severity: Severity
    confidence: Confidence
    cvss_score: float | None
    cvss_version: str | None
    epss_score: float | None
    epss_percentile: float | None
    kev: bool | None  # null = unknown (CISA KEV catalog never synced)
    asset_criticality: AssetCriticality | None  # null = finding not linked to a registered Asset


class RiskComponentResponse(BaseModel):
    name: str
    value: float
    weight: float
    available: bool


class RiskDetailResponse(BaseModel):
    finding_id: uuid.UUID
    score: int
    priority: RiskPriority
    raw_score: float
    criticality_multiplier: float
    confidence_multiplier: float
    inputs: RiskInputsResponse
    components: list[RiskComponentResponse]
    explanation: list[str]
    calculated_at: datetime


class AssetRiskSummaryResponse(BaseModel):
    asset_id: uuid.UUID
    total_findings: int
    critical_findings: int
    high_findings: int
    medium_findings: int
    low_findings: int
    informational_findings: int
    kev_findings: int
    highest_risk_score: int | None
    unscored_findings: int  # findings with no CVE / no risk computed yet
