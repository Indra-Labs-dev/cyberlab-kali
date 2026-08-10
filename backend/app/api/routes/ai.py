import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.analyst import AIAnalyst
from app.ai.ollama import OllamaProvider, OllamaUnavailableError
from app.ai.planner import AIMissionPlanner
from app.ai.schemas import AnalysisResult, ChatResponse, MissionPlan
from app.db.session import get_db
from app.models.job import Job

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
    target: str
    goal: str


@router.post("/plan", response_model=MissionPlan)
async def plan_mission(request: PlanRequest, provider: OllamaProvider = Depends(get_provider)) -> MissionPlan:
    planner = AIMissionPlanner(provider)
    try:
        return await planner.plan(request.target, request.goal)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class ChatRequest(BaseModel):
    message: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, provider: OllamaProvider = Depends(get_provider)) -> ChatResponse:
    try:
        reply = await provider.generate(request.message, system=CHAT_SYSTEM)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(reply=reply)
