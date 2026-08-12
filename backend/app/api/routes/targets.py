import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.job import Job
from app.models.target import AuthorizationStatus, Target, TargetType
from app.schemas.job import JobResponse
from app.schemas.target import TargetResponse, TargetUpdateRequest
from app.scheduling.service import disable_schedules_for_asset

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=list[TargetResponse])
async def list_targets(
    project_id: uuid.UUID | None = Query(default=None),
    target_type: TargetType | None = Query(default=None),
    authorization_status: AuthorizationStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[Target]:
    stmt = select(Target).order_by(Target.created_at.desc())
    if project_id is not None:
        stmt = stmt.where(Target.project_id == project_id)
    if target_type is not None:
        stmt = stmt.where(Target.target_type == target_type)
    if authorization_status is not None:
        stmt = stmt.where(Target.authorization_status == authorization_status)
    if search:
        stmt = stmt.where(Target.name.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{target_id}", response_model=TargetResponse)
async def get_target(target_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Target:
    target = await db.get(Target, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")
    return target


@router.patch("/{target_id}", response_model=TargetResponse)
async def update_target(
    target_id: uuid.UUID, request: TargetUpdateRequest, db: AsyncSession = Depends(get_db)
) -> Target:
    target = await db.get(Target, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")

    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(target, field, value)

    if not (target.hostname or target.ip_address or target.url):
        raise HTTPException(status_code=422, detail="at least one of hostname, ip_address, or url is required")

    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/{target_id}", status_code=204)
async def delete_target(target_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    target = await db.get(Target, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")
    # Target IS Asset (Phase 13, same table) -- same schedule cleanup as
    # DELETE /api/assets/{id} (Phase 14).
    await disable_schedules_for_asset(db, target_id)
    await db.delete(target)
    await db.commit()


@router.get("/{target_id}/jobs", response_model=list[JobResponse])
async def list_target_jobs(target_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[Job]:
    target = await db.get(Target, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")

    result = await db.execute(select(Job).where(Job.target_id == target_id).order_by(Job.created_at.desc()))
    return list(result.scalars().all())
