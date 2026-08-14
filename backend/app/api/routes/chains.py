"""Phase 21 -- Tool Orchestrator: MissionTemplate CRUD + ChainRun
lifecycle. Deliberately its own router (not folded into app/api/routes/ai.py):
a MissionTemplate has no AI involvement at all. See app/chains/service.py
for the full architecture.
"""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.service import ChainRunNotFoundError, cancel_chain_run, create_chain_run
from app.core.rate_limit import chain_run_limit
from app.db.session import get_db
from app.models.asset import Asset
from app.models.mission_template import ChainRun, ChainRunStatus, ChainRunStep, MissionTemplate, MissionTemplateStep
from app.schemas.mission_template import (
    ChainRunCreateRequest,
    ChainRunResponse,
    MissionTemplateCreateRequest,
    MissionTemplateResponse,
)

router = APIRouter(prefix="/chains", tags=["chains"])


# --------------------------------------------------------------------------
# MissionTemplate -- reusable, human-authored chain definitions
# --------------------------------------------------------------------------


async def _template_response(db: AsyncSession, template: MissionTemplate) -> MissionTemplateResponse:
    steps = (
        await db.execute(
            select(MissionTemplateStep)
            .where(MissionTemplateStep.template_id == template.id)
            .order_by(MissionTemplateStep.step_order)
        )
    ).scalars()
    return MissionTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        created_at=template.created_at,
        steps=list(steps),
    )


@router.post("/templates", response_model=MissionTemplateResponse, status_code=201)
async def create_template(request: MissionTemplateCreateRequest, db: AsyncSession = Depends(get_db)) -> MissionTemplateResponse:
    template = MissionTemplate(name=request.name, description=request.description)
    db.add(template)
    await db.flush()

    for order, step in enumerate(request.steps):
        db.add(
            MissionTemplateStep(
                template_id=template.id,
                step_order=order,
                tool=step.tool,
                profile=step.profile,
                options=step.options,
                condition_type=step.condition_type,
                condition_params=step.condition_params,
            )
        )
    await db.commit()
    await db.refresh(template)
    return await _template_response(db, template)


@router.get("/templates", response_model=list[MissionTemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[MissionTemplateResponse]:
    templates = (await db.execute(select(MissionTemplate).order_by(MissionTemplate.created_at.desc()))).scalars()
    return [await _template_response(db, template) for template in templates]


@router.get("/templates/{template_id}", response_model=MissionTemplateResponse)
async def get_template(template_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> MissionTemplateResponse:
    template = await db.get(MissionTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    return await _template_response(db, template)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    template = await db.get(MissionTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    # ChainRun.template_id is ON DELETE SET NULL -- deleting a template
    # never destroys run history, each ChainRunStep already snapshots its
    # own tool/profile/options/condition at creation time.
    await db.delete(template)
    await db.commit()


# --------------------------------------------------------------------------
# ChainRun -- one execution of a template against a real target. Starting
# a run is itself the human's deliberate action -- no separate approval
# step (contrast with Phase 18's Mission, which needs one because an
# AI-proposed plan needs review; a template a human already authored does
# not).
# --------------------------------------------------------------------------


async def _run_response(db: AsyncSession, run: ChainRun) -> ChainRunResponse:
    steps = (
        await db.execute(
            select(ChainRunStep).where(ChainRunStep.chain_run_id == run.id).order_by(ChainRunStep.step_order)
        )
    ).scalars()
    return ChainRunResponse(
        id=run.id,
        template_id=run.template_id,
        target_id=run.target_id,
        project_id=run.project_id,
        status=run.status,
        created_at=run.created_at,
        finished_at=run.finished_at,
        steps=list(steps),
    )


@router.post("/runs", response_model=ChainRunResponse, status_code=201, dependencies=[Depends(chain_run_limit)])
async def create_run(request: ChainRunCreateRequest, db: AsyncSession = Depends(get_db)) -> ChainRunResponse:
    # Existence pre-checks here give a clear 404 message distinguishing
    # "no such template" from "no such target" -- create_chain_run() itself
    # only returns None either way (it re-fetches inside its own sync
    # session regardless, so this isn't a duplicated authority, just a
    # clearer error message for the caller).
    template = await db.get(MissionTemplate, request.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    asset = await db.get(Asset, request.target_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="target not found")

    # Sync, DB-writing function -- asyncio.to_thread is the same bridge
    # idiom already used for approve_mission()/regenerate_project_summary_route
    # (Phase 18/19).
    run = await asyncio.to_thread(create_chain_run, request.template_id, request.target_id)
    if run is None:
        raise HTTPException(status_code=400, detail="template has no steps")
    return await _run_response(db, run)


@router.get("/runs", response_model=list[ChainRunResponse])
async def list_runs(
    target_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    template_id: uuid.UUID | None = Query(default=None),
    status: ChainRunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ChainRunResponse]:
    stmt = select(ChainRun).order_by(ChainRun.created_at.desc()).limit(limit)
    if target_id is not None:
        stmt = stmt.where(ChainRun.target_id == target_id)
    if project_id is not None:
        stmt = stmt.where(ChainRun.project_id == project_id)
    if template_id is not None:
        stmt = stmt.where(ChainRun.template_id == template_id)
    if status is not None:
        stmt = stmt.where(ChainRun.status == status)
    runs = (await db.execute(stmt)).scalars()
    return [await _run_response(db, run) for run in runs]


@router.get("/runs/{run_id}", response_model=ChainRunResponse)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ChainRunResponse:
    run = await db.get(ChainRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="chain run not found")
    return await _run_response(db, run)


@router.post("/runs/{run_id}/cancel", response_model=ChainRunResponse)
async def cancel_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ChainRunResponse:
    # Kill switch. Never touches an in-flight Job -- that's still
    # POST /api/jobs/{id}/cancel; this only prevents any future step.
    try:
        run = await asyncio.to_thread(cancel_chain_run, run_id)
    except ChainRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _run_response(db, run)
