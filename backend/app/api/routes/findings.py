import uuid
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.asset import Asset
from app.models.finding import Finding, RiskPriority, Severity
from app.models.job import Job
from app.models.vulnerability_intel import VulnerabilityIntel
from app.risk.calculator import RiskInputs, calculate_risk
from app.schemas.finding import FindingResponse
from app.schemas.risk import RiskComponentResponse, RiskDetailResponse, RiskInputsResponse

router = APIRouter(prefix="/findings", tags=["findings"])


class FindingSort(str, Enum):
    CREATED_DESC = "created_at_desc"
    RISK_DESC = "risk_score_desc"
    RISK_ASC = "risk_score_asc"


@router.get("", response_model=list[FindingResponse])
async def list_findings(
    severity: Severity | None = Query(default=None),
    job_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    priority: RiskPriority | None = Query(default=None),
    kev: bool | None = Query(default=None),
    min_risk_score: int | None = Query(default=None, ge=0, le=100),
    sort: FindingSort = Query(default=FindingSort.CREATED_DESC),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[Finding]:
    stmt = select(Finding)
    if severity is not None:
        stmt = stmt.where(Finding.severity == severity)
    if job_id is not None:
        stmt = stmt.where(Finding.job_id == job_id)
    if priority is not None:
        stmt = stmt.where(Finding.risk_priority == priority)
    if kev is not None:
        stmt = stmt.where(Finding.kev == kev)
    if min_risk_score is not None:
        stmt = stmt.where(Finding.risk_score >= min_risk_score)
    if project_id is not None or target_id is not None:
        stmt = stmt.join(Job, Finding.job_id == Job.id)
        if project_id is not None:
            stmt = stmt.where(Job.project_id == project_id)
        if target_id is not None:
            stmt = stmt.where(Job.target_id == target_id)

    if sort == FindingSort.RISK_DESC:
        stmt = stmt.order_by(Finding.risk_score.desc().nulls_last(), Finding.created_at.desc())
    elif sort == FindingSort.RISK_ASC:
        stmt = stmt.order_by(Finding.risk_score.asc().nulls_last(), Finding.created_at.desc())
    else:
        stmt = stmt.order_by(Finding.created_at.desc())
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{finding_id}", response_model=FindingResponse)
async def get_finding(finding_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Finding:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return finding


@router.get("/{finding_id}/risk", response_model=RiskDetailResponse)
async def get_finding_risk(finding_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> RiskDetailResponse:
    """Live-recomputed from the same local data the materialized
    Finding.risk_score cache was built from (never a network call -- see
    app/risk/calculator.py) so this is always exactly reproducible, not just
    "whatever was cached last time".
    """
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")

    cvss_version = epss_percentile = None
    if finding.cve_ids:
        intel_rows = (
            await db.execute(select(VulnerabilityIntel).where(VulnerabilityIntel.cve.in_(finding.cve_ids)))
        ).scalars().all()
        cvss_rows = [r for r in intel_rows if r.cvss_score is not None]
        if cvss_rows:
            cvss_version = max(cvss_rows, key=lambda r: r.cvss_score).cvss_version
        epss_rows = [r for r in intel_rows if r.epss_score is not None]
        if epss_rows:
            epss_percentile = max(epss_rows, key=lambda r: r.epss_score).epss_percentile

    asset_criticality = None
    job = await db.get(Job, finding.job_id)
    if job is not None and job.target_id is not None:
        asset = await db.get(Asset, job.target_id)
        if asset is not None:
            asset_criticality = asset.criticality

    inputs = RiskInputs(
        severity=finding.severity,
        confidence=finding.confidence,
        cvss_score=finding.cvss_score,
        cvss_version=cvss_version,
        epss_score=finding.epss_score,
        epss_percentile=epss_percentile,
        kev=finding.kev,
        asset_criticality=asset_criticality,
    )
    result = calculate_risk(inputs)

    return RiskDetailResponse(
        finding_id=finding.id,
        score=result.score,
        priority=result.priority,
        raw_score=result.raw_score,
        criticality_multiplier=result.criticality_multiplier,
        confidence_multiplier=result.confidence_multiplier,
        inputs=RiskInputsResponse(
            severity=inputs.severity,
            confidence=inputs.confidence,
            cvss_score=inputs.cvss_score,
            cvss_version=inputs.cvss_version,
            epss_score=inputs.epss_score,
            epss_percentile=inputs.epss_percentile,
            kev=inputs.kev,
            asset_criticality=inputs.asset_criticality,
        ),
        components=[
            RiskComponentResponse(name=c.name, value=c.value, weight=c.weight, available=c.available)
            for c in result.components
        ],
        explanation=result.explanation,
        calculated_at=finding.risk_calculated_at or datetime.now(timezone.utc),
    )
