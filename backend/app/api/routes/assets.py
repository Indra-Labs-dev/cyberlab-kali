import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.asset import Asset, AssetCriticality, AssetType, AuthorizationStatus
from app.models.job import Job
from app.schemas.asset import AssetResponse, AssetUpdateRequest
from app.schemas.job import JobResponse
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
    for field, value in updates.items():
        setattr(asset, field, value)

    if not (asset.hostname or asset.ip_address or asset.url):
        raise HTTPException(status_code=422, detail="at least one of hostname, ip_address, or url is required")

    await db.commit()
    await db.refresh(asset)
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
