import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.correlation import CorrelationAgent
from app.ai.agents.report import ReportAgent
from app.ai.analyst import AIAnalyst
from app.ai.ollama import OllamaProvider, OllamaUnavailableError
from app.ai.orchestrator import (
    InvalidMissionStateError,
    MissionNotFoundError,
    MissionOrchestrator,
    approve_mission,
    cancel_mission,
)
from app.ai.planner import AIMissionPlanner
from app.ai.prompts import build_tool_catalog_summary
from app.ai.schemas import AnalysisResult, ChatResponse, MissionPlan, ReportProposal
from app.db.session import get_db
from app.models.ai_correlation_suggestion import AICorrelationSuggestion, SuggestionStatus
from app.models.finding import Finding
from app.models.finding_relation import FindingRelation
from app.models.job import Job, JobStatus
from app.models.mission import Mission, MissionStep
from app.models.project import Project
from app.models.target import Target
from app.schemas.ai_correlation import AICorrelationSuggestionResponse, GenerateCorrelationSuggestionsRequest
from app.schemas.mission import MissionCreateRequest, MissionResponse, MissionStepResponse
from app.tools import registry

router = APIRouter(prefix="/ai", tags=["ai"])

CHAT_SYSTEM = """You are the CyberLab AI Assistant, embedded in a local cybersecurity lab tool \
used only for authorized testing (CTF, labs, pentest with permission, auditing systems the user \
owns). Answer questions about security concepts, the scan results the user shares, and how to \
use CyberLab. Never help attack systems without authorization; if asked to, explain you can't.

When asked what tools are available, answer ONLY from the list below -- these are the tools \
actually registered and runnable in this CyberLab instance. Never mention a tool that isn't in \
this list, even if you know of it in general (e.g. commercial scanners, tools not installed here).

Available tools:
{tool_catalog}"""


def get_provider() -> OllamaProvider:
    return OllamaProvider()


@router.post("/analyze/{job_id}", response_model=AnalysisResult)
async def analyze_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    provider: OllamaProvider = Depends(get_provider),
) -> AnalysisResult:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in ("SUCCESS", "FAILED"):
        raise HTTPException(status_code=400, detail=f"job is {job.status.value}, nothing to analyze yet")

    analyst = AIAnalyst(provider)
    try:
        analysis = await analyst.analyze(
            tool=job.tool,
            target=job.target,
            exit_code=job.exit_code,
            parsed_result=job.result or {},
            stdout=job.stdout or "",
        )
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    job.ai_analysis = analysis.model_dump()
    await db.commit()
    return analysis


class PlanRequest(BaseModel):
    # Either a free-text target (quick/unregistered) or target_id (a real
    # Target, resolved server-side -- the model is never trusted with a real
    # address it wasn't given, and never invents/chooses one).
    target: str | None = None
    target_id: uuid.UUID | None = None
    goal: str

    @model_validator(mode="after")
    def _require_target_or_target_id(self) -> "PlanRequest":
        if not self.target and not self.target_id:
            raise ValueError("either target or target_id is required")
        return self


@router.post("/plan", response_model=MissionPlan)
async def plan_mission(
    request: PlanRequest, db: AsyncSession = Depends(get_db), provider: OllamaProvider = Depends(get_provider)
) -> MissionPlan:
    target_address = request.target
    authorization_status = None
    target_id = request.target_id

    if request.target_id is not None:
        target = await db.get(Target, request.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="target not found")
        target_address = target.address
        authorization_status = target.authorization_status.value

    planner = AIMissionPlanner(provider)
    try:
        return await planner.plan(target_address, request.goal, target_id=target_id, authorization_status=authorization_status)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class ChatRequest(BaseModel):
    message: str
    # Optional context so "analyze this target" resolves to a real Target
    # the AI is TOLD about, rather than something it has to invent.
    target_id: uuid.UUID | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest, db: AsyncSession = Depends(get_db), provider: OllamaProvider = Depends(get_provider)
) -> ChatResponse:
    ai_visible_tools = [tool.model_dump() for tool in registry.list_tools() if tool.ai_allowed]
    system = CHAT_SYSTEM.format(tool_catalog=build_tool_catalog_summary(ai_visible_tools))
    if request.target_id is not None:
        target = await db.get(Target, request.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="target not found")
        system += (
            f"\n\nActive target context (read-only -- you cannot change this): "
            f"name={target.name!r}, address={target.address!r}, "
            f"authorization_status={target.authorization_status.value}. "
            f"If the user refers to 'this target' or 'the current target', they mean this one."
        )

    try:
        reply = await provider.generate(request.message, system=system)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(reply=reply)


# --------------------------------------------------------------------------
# Phase 18 -- Missions (autonomy Level 2: approve a plan, then it executes
# one re-validated step at a time). See app/ai/orchestrator.py; nothing
# here duplicates its logic, this module only does request/response
# translation and the async<->sync bridge for the sync orchestrator calls.
# --------------------------------------------------------------------------


async def _mission_response(db: AsyncSession, mission: Mission) -> MissionResponse:
    steps = (
        await db.execute(select(MissionStep).where(MissionStep.mission_id == mission.id).order_by(MissionStep.step_order))
    ).scalars().all()
    return MissionResponse(
        id=mission.id,
        project_id=mission.project_id,
        target_id=mission.target_id,
        goal=mission.goal,
        status=mission.status,
        max_steps=mission.max_steps,
        created_at=mission.created_at,
        approved_at=mission.approved_at,
        finished_at=mission.finished_at,
        steps=[MissionStepResponse.model_validate(step) for step in steps],
    )


@router.post("/missions", response_model=MissionResponse, status_code=201)
async def create_mission(
    request: MissionCreateRequest, db: AsyncSession = Depends(get_db), provider: OllamaProvider = Depends(get_provider)
) -> MissionResponse:
    # This is the ONLY place target_id is resolved -- the orchestrator
    # itself never looks up an id, it only ever receives an already-loaded
    # Asset, so it can never be tricked into acting on anything the model
    # output (same enforcement shape as POST /api/ai/plan and POST /api/jobs).
    target = await db.get(Target, request.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")

    orchestrator = MissionOrchestrator(provider)
    try:
        mission = await orchestrator.create_mission(db, target=target, goal=request.goal, max_steps=request.max_steps)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return await _mission_response(db, mission)


@router.get("/missions", response_model=list[MissionResponse])
async def list_missions(
    target_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[MissionResponse]:
    stmt = select(Mission).order_by(Mission.created_at.desc()).limit(limit)
    if target_id is not None:
        stmt = stmt.where(Mission.target_id == target_id)
    missions = (await db.execute(stmt)).scalars().all()
    return [await _mission_response(db, mission) for mission in missions]


@router.get("/missions/{mission_id}", response_model=MissionResponse)
async def get_mission(mission_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> MissionResponse:
    mission = await db.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="mission not found")
    return await _mission_response(db, mission)


@router.post("/missions/{mission_id}/approve", response_model=MissionResponse)
async def approve_mission_route(mission_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> MissionResponse:
    # approve_mission() is sync (it locks a row and, via advance_mission(),
    # creates a real Job through the same is_executable()/prepare_job() pair
    # ticker.py uses) -- asyncio.to_thread is the same bridge idiom already
    # used by app/api/routes/assets.py for recalculate_findings_for_asset_sync.
    try:
        mission = await asyncio.to_thread(approve_mission, mission_id)
    except MissionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidMissionStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _mission_response(db, mission)


@router.post("/missions/{mission_id}/cancel", response_model=MissionResponse)
async def cancel_mission_route(mission_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> MissionResponse:
    # Kill switch. Never touches an in-flight Job -- that's still
    # POST /api/jobs/{id}/cancel; this only prevents any future step.
    try:
        mission = await asyncio.to_thread(cancel_mission, mission_id)
    except MissionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _mission_response(db, mission)


# --------------------------------------------------------------------------
# Phase 18.8 -- Correlation Agent suggestions. FindingRelation (Phase 16)
# stays reserved for the deterministic engine (app/findings/correlation.py)
# -- a suggestion here is never written there directly, and never becomes
# one automatically. RULE_AI_ACCEPTED is a distinct rule string so an
# AI-originated relation is always traceable back to a human "Accept".
# --------------------------------------------------------------------------

RULE_AI_ACCEPTED = "RULE_AI_ACCEPTED"


@router.post("/correlation-suggestions", response_model=list[AICorrelationSuggestionResponse])
async def generate_correlation_suggestions(
    request: GenerateCorrelationSuggestionsRequest,
    db: AsyncSession = Depends(get_db),
    provider: OllamaProvider = Depends(get_provider),
) -> list[AICorrelationSuggestionResponse]:
    target = await db.get(Target, request.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")

    findings = list(
        (
            await db.execute(select(Finding).join(Job, Finding.job_id == Job.id).where(Job.target_id == request.target_id))
        ).scalars()
    )

    agent = CorrelationAgent(provider)
    try:
        suggestions = await agent.suggest(findings)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    created: list[AICorrelationSuggestion] = []
    for item in suggestions:
        # Same canonical-pair ordering as FindingRelation's own writer
        # (app/findings/correlation.py::_create_relation_if_new) -- but
        # duplicated here deliberately, not imported: that helper is
        # private to the deterministic engine, and this route never writes
        # a FindingRelation directly anyway, only an AICorrelationSuggestion.
        ordered = sorted((item.finding_id, item.related_finding_id), key=str)
        left, right = ordered[0], ordered[1]

        existing = await db.execute(
            select(AICorrelationSuggestion).where(
                AICorrelationSuggestion.finding_id == left, AICorrelationSuggestion.related_finding_id == right
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        row = AICorrelationSuggestion(
            finding_id=left, related_finding_id=right, rationale=item.rationale, status=SuggestionStatus.PENDING
        )
        db.add(row)
        created.append(row)

    await db.commit()
    for row in created:
        await db.refresh(row)

    all_suggestions = await _list_suggestions_for_target(db, request.target_id)
    return all_suggestions


async def _list_suggestions_for_target(db: AsyncSession, target_id: uuid.UUID) -> list[AICorrelationSuggestionResponse]:
    # Both findings in a suggestion always come from the same asset (the
    # pair is only ever generated from one asset's finding set, see
    # generate_correlation_suggestions above) -- joining on finding_id
    # alone (whichever of the pair sorted first) is enough to scope by
    # target, no need to check related_finding_id too.
    stmt = (
        select(AICorrelationSuggestion)
        .join(Finding, AICorrelationSuggestion.finding_id == Finding.id)
        .join(Job, Finding.job_id == Job.id)
        .where(Job.target_id == target_id)
        .order_by(AICorrelationSuggestion.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [AICorrelationSuggestionResponse.model_validate(row) for row in rows]


@router.get("/correlation-suggestions", response_model=list[AICorrelationSuggestionResponse])
async def list_correlation_suggestions(
    target_id: uuid.UUID = Query(...), db: AsyncSession = Depends(get_db)
) -> list[AICorrelationSuggestionResponse]:
    return await _list_suggestions_for_target(db, target_id)


@router.post("/correlation-suggestions/{suggestion_id}/accept", response_model=AICorrelationSuggestionResponse)
async def accept_correlation_suggestion(
    suggestion_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AICorrelationSuggestionResponse:
    suggestion = await db.get(AICorrelationSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="suggestion not found")
    if suggestion.status == SuggestionStatus.DISMISSED:
        raise HTTPException(status_code=400, detail="suggestion was already dismissed, cannot accept")
    if suggestion.status == SuggestionStatus.ACCEPTED:
        return AICorrelationSuggestionResponse.model_validate(suggestion)  # idempotent no-op

    # Revalidate both Findings still exist -- ai_correlation_suggestions
    # cascades on Finding delete, so this should be unreachable, but a
    # human action turning into a real FindingRelation is exactly the kind
    # of write that must never trust stale state.
    finding_a = await db.get(Finding, suggestion.finding_id)
    finding_b = await db.get(Finding, suggestion.related_finding_id)
    if finding_a is None or finding_b is None:
        raise HTTPException(status_code=404, detail="one or both findings no longer exist")

    ordered = sorted((finding_a.id, finding_b.id), key=str)
    left, right = ordered[0], ordered[1]
    existing_relation = await db.execute(
        select(FindingRelation).where(
            FindingRelation.finding_id == left,
            FindingRelation.related_finding_id == right,
            FindingRelation.rule == RULE_AI_ACCEPTED,
        )
    )
    if existing_relation.scalar_one_or_none() is None:
        db.add(
            FindingRelation(
                finding_id=left,
                related_finding_id=right,
                rule=RULE_AI_ACCEPTED,
                reason=suggestion.rationale or "Accepted AI correlation suggestion.",
                relation_metadata={"suggestion_id": str(suggestion.id)},
            )
        )

    suggestion.status = SuggestionStatus.ACCEPTED
    suggestion.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(suggestion)
    return AICorrelationSuggestionResponse.model_validate(suggestion)


@router.post("/correlation-suggestions/{suggestion_id}/dismiss", response_model=AICorrelationSuggestionResponse)
async def dismiss_correlation_suggestion(
    suggestion_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AICorrelationSuggestionResponse:
    suggestion = await db.get(AICorrelationSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="suggestion not found")
    if suggestion.status == SuggestionStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="suggestion was already accepted, cannot dismiss")
    if suggestion.status == SuggestionStatus.DISMISSED:
        return AICorrelationSuggestionResponse.model_validate(suggestion)  # idempotent no-op

    suggestion.status = SuggestionStatus.DISMISSED
    suggestion.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(suggestion)
    return AICorrelationSuggestionResponse.model_validate(suggestion)


# --------------------------------------------------------------------------
# Phase 18.9 -- Report Agent. Only ever returns a ReportProposal for a human
# to review/edit -- never calls build_report_data()/render(), never creates
# a Report. Real generation stays exactly POST /api/reports, untouched.
# --------------------------------------------------------------------------


class ReportProposalRequest(BaseModel):
    project_id: uuid.UUID


@router.post("/reports/propose", response_model=ReportProposal)
async def propose_report(
    request: ReportProposalRequest, db: AsyncSession = Depends(get_db), provider: OllamaProvider = Depends(get_provider)
) -> ReportProposal:
    project = await db.get(Project, request.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    jobs = list(
        (
            await db.execute(
                select(Job).where(Job.project_id == request.project_id, Job.status == JobStatus.SUCCESS).order_by(Job.created_at)
            )
        ).scalars()
    )

    agent = ReportAgent(provider)
    try:
        return await agent.propose(project.name, jobs)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
