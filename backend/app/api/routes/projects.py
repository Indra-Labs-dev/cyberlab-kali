import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.finding import Finding
from app.models.job import Job
from app.models.project import Project, ProjectStatus
from app.models.target import Target
from app.schemas.project import ProjectCreateRequest, ProjectResponse, ProjectSummary, ProjectUpdateRequest
from app.schemas.target import TargetCreateRequest, TargetResponse
from app.targets.authorization import infer_default_authorization

router = APIRouter(prefix="/projects", tags=["projects"])


async def _summarize(db: AsyncSession, project: Project) -> ProjectSummary:
    target_count = await db.scalar(select(func.count()).select_from(Target).where(Target.project_id == project.id))
    job_count = await db.scalar(select(func.count()).select_from(Job).where(Job.project_id == project.id))
    finding_count = await db.scalar(
        select(func.count()).select_from(Finding).join(Job, Finding.job_id == Job.id).where(Job.project_id == project.id)
    )
    return ProjectSummary(
        **ProjectResponse.model_validate(project).model_dump(),
        target_count=target_count or 0,
        job_count=job_count or 0,
        finding_count=finding_count or 0,
        # Labs are not yet associated with projects -- the Lab Manager has no
        # concept of a project, labs remain a global resource. See docs/labs.md.
        lab_count=0,
    )


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    status: ProjectStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectSummary]:
    stmt = select(Project).order_by(Project.created_at.desc())
    if status is not None:
        stmt = stmt.where(Project.status == status)
    if search:
        stmt = stmt.where(Project.name.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    projects = list(result.scalars().all())
    return [await _summarize(db, p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(request: ProjectCreateRequest, db: AsyncSession = Depends(get_db)) -> Project:
    project = Project(name=request.name, description=request.description)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectSummary)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectSummary:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return await _summarize(db, project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID, request: ProjectUpdateRequest, db: AsyncSession = Depends(get_db)
) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    await db.delete(project)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="project still has targets; delete or reassign them first",
        ) from exc


@router.get("/{project_id}/targets", response_model=list[TargetResponse])
async def list_project_targets(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[Target]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    result = await db.execute(select(Target).where(Target.project_id == project_id).order_by(Target.created_at.desc()))
    return list(result.scalars().all())


@router.post("/{project_id}/targets", response_model=TargetResponse, status_code=201)
async def create_project_target(
    project_id: uuid.UUID, request: TargetCreateRequest, db: AsyncSession = Depends(get_db)
) -> Target:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    authorization_status = request.authorization_status or infer_default_authorization(
        request.hostname, request.ip_address, request.url
    )

    target = Target(
        project_id=project_id,
        name=request.name,
        hostname=request.hostname,
        ip_address=request.ip_address,
        url=request.url,
        target_type=request.target_type,
        authorization_status=authorization_status,
        description=request.description,
        target_metadata=request.target_metadata,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return target
