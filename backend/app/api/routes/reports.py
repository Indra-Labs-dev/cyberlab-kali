import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import report_generation_limit
from app.db.session import get_db
from app.models.report import Report
from app.reports.builder import NoJobsFoundError, build_report_data
from app.reports.renderers import render
from app.schemas.report import ReportCreateRequest, ReportMeta

router = APIRouter(prefix="/reports", tags=["reports"])

_CONTENT_TYPES = {
    "json": "application/json",
    "markdown": "text/markdown",
    "html": "text/html",
    "pdf": "application/pdf",
}


@router.post("", response_model=ReportMeta, status_code=201, dependencies=[Depends(report_generation_limit)])
async def create_report(request: ReportCreateRequest, db: AsyncSession = Depends(get_db)) -> Report:
    try:
        data = await build_report_data(db, request.job_ids, request.title)
    except NoJobsFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    content, _is_binary = render(request.format.value, data, request.template.value)

    report = Report(
        title=request.title,
        format=request.format,
        template=request.template,
        job_ids=[str(j) for j in request.job_ids],
        content=content,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


@router.get("", response_model=list[ReportMeta])
async def list_reports(db: AsyncSession = Depends(get_db)) -> list[Report]:
    result = await db.execute(select(Report).order_by(Report.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{report_id}", response_model=ReportMeta)
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Report:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.get("/{report_id}/download")
async def download_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")

    media_type = _CONTENT_TYPES[report.format.value]
    extension = "md" if report.format.value == "markdown" else report.format.value
    filename = f"cyberlab-report-{report.id}.{extension}"

    if report.format.value == "pdf":
        body = base64.b64decode(report.content)
    else:
        body = report.content.encode("utf-8")

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
