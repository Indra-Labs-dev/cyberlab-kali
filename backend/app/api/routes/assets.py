import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.asset import Asset, AssetCriticality, AssetType, AuthorizationStatus
from app.models.finding import Finding, RiskPriority
from app.models.job import Job
from app.risk.service import recalculate_findings_for_asset_sync
from app.schemas.asset import AssetResponse, AssetUpdateRequest
from app.schemas.job import JobResponse
from app.schemas.risk import AssetRiskSummaryResponse
from app.scheduling.service import disable_schedules_for_asset

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetResponse])
async def list_assets(
    project_id: uuid.UUID | None = Query(default=None),
    type: AssetType | None = Query(default=None),
    criticality: AssetCriticality | None = Query(default=None),
    authorization_status: AuthorizationStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[Asset]:
    stmt = select(Asset).order_by(Asset.created_at.desc())
    if project_id is not None:
        stmt = stmt.where(Asset.project_id == project_id)
    if type is not None:
        stmt = stmt.where(Asset.type == type)
    if criticality is not None:
        stmt = stmt.where(Asset.criticality == criticality)
    if authorization_status is not None:
        stmt = stmt.where(Asset.authorization_status == authorization_status)
    if search:
        stmt = stmt.where(Asset.name.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Asset:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset


@router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: uuid.UUID, request: AssetUpdateRequest, db: AsyncSession = Depends(get_db)
) -> Asset:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    updates = request.model_dump(exclude_unset=True)
    criticality_changed = "criticality" in updates and updates["criticality"] != asset.criticality
    for field, value in updates.items():
        setattr(asset, field, value)

    if not (asset.hostname or asset.ip_address or asset.url):
        raise HTTPException(status_code=422, detail="at least one of hostname, ip_address, or url is required")

    await db.commit()
    await db.refresh(asset)

    if criticality_changed:
        # Risk Score depends on Asset criticality (Phase 15) -- every
        # Finding on this asset needs its materialized score recomputed.
        # Runs in a thread (own sync session) so this admin action, however
        # many findings it touches, never blocks the event loop.
        await asyncio.to_thread(recalculate_findings_for_asset_sync, asset_id)

    return asset


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    # Same transaction as the delete: any ScheduledJob pointing at this
    # asset is disabled cleanly rather than left ACTIVE with a dangling
    # asset_id for the ticker to trip over later (Phase 14).
    await disable_schedules_for_asset(db, asset_id)
    await db.delete(asset)
    await db.commit()


@router.get("/{asset_id}/jobs", response_model=list[JobResponse])
async def list_asset_jobs(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[Job]:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    result = await db.execute(select(Job).where(Job.target_id == asset_id).order_by(Job.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{asset_id}/risk-summary", response_model=AssetRiskSummaryResponse)
async def get_asset_risk_summary(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AssetRiskSummaryResponse:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    job_ids = (await db.execute(select(Job.id).where(Job.target_id == asset_id))).scalars().all()
    findings = []
    if job_ids:
        findings = (await db.execute(select(Finding).where(Finding.job_id.in_(job_ids)))).scalars().all()

    counts = {p: 0 for p in RiskPriority}
    kev_findings = 0
    unscored = 0
    highest: int | None = None
    for finding in findings:
        if finding.risk_priority is not None:
            counts[finding.risk_priority] += 1
        else:
            unscored += 1
        if finding.kev:
            kev_findings += 1
        if finding.risk_score is not None:
            highest = finding.risk_score if highest is None else max(highest, finding.risk_score)

    return AssetRiskSummaryResponse(
        asset_id=asset_id,
        total_findings=len(findings),
        critical_findings=counts[RiskPriority.CRITICAL],
        high_findings=counts[RiskPriority.HIGH],
        medium_findings=counts[RiskPriority.MEDIUM],
        low_findings=counts[RiskPriority.LOW],
        informational_findings=counts[RiskPriority.INFORMATIONAL],
        kev_findings=kev_findings,
        highest_risk_score=highest,
        unscored_findings=unscored,
    )
