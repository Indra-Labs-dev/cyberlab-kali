import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.finding import Finding, Severity
from app.models.job import Job
from app.schemas.finding import FindingResponse

router = APIRouter(prefix="/findings", tags=["findings"])


@router.get("", response_model=list[FindingResponse])
async def list_findings(
    severity: Severity | None = Query(default=None),
    job_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[Finding]:
    stmt = select(Finding).order_by(Finding.created_at.desc()).limit(limit)
    if severity is not None:
        stmt = stmt.where(Finding.severity == severity)
    if job_id is not None:
        stmt = stmt.where(Finding.job_id == job_id)
    if project_id is not None or target_id is not None:
        stmt = stmt.join(Job, Finding.job_id == Job.id)
        if project_id is not None:
            stmt = stmt.where(Job.project_id == project_id)
        if target_id is not None:
            stmt = stmt.where(Job.target_id == target_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{finding_id}", response_model=FindingResponse)
async def get_finding(finding_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Finding:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return finding
