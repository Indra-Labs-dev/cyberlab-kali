import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.analyst import AIAnalyst
from app.ai.ollama import OllamaProvider, OllamaUnavailableError
from app.ai.planner import AIMissionPlanner
from app.ai.schemas import AnalysisResult, ChatResponse, MissionPlan
from app.db.session import get_db
from app.models.job import Job
from app.models.target import Target

router = APIRouter(prefix="/ai", tags=["ai"])

CHAT_SYSTEM = """You are the CyberLab AI Assistant, embedded in a local cybersecurity lab tool \
used only for authorized testing (CTF, labs, pentest with permission, auditing systems the user \
owns). Answer questions about security concepts, the scan results the user shares, and how to \
use CyberLab. Never help attack systems without authorization; if asked to, explain you can't."""


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
    system = CHAT_SYSTEM
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
