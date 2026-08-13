import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finding import Finding
from app.models.job import Job


class NoJobsFoundError(ValueError):
    pass


async def build_report_data(db: AsyncSession, job_ids: list[uuid.UUID], title: str) -> dict:
    jobs_result = await db.execute(select(Job).where(Job.id.in_(job_ids)).order_by(Job.created_at))
    jobs = list(jobs_result.scalars().all())
    if not jobs:
        raise NoJobsFoundError("none of the given job ids were found")

    findings_result = await db.execute(
        select(Finding).where(Finding.job_id.in_([j.id for j in jobs])).order_by(Finding.severity, Finding.created_at)
    )
    findings = list(findings_result.scalars().all())

    by_severity: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity.value] = by_severity.get(finding.severity.value, 0) + 1

    targets = sorted({job.target for job in jobs})
    tools_used = sorted({job.tool for job in jobs})

    return {
        "title": title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"targets": targets, "tools_used": tools_used},
        "executive_summary": {
            "total_jobs": len(jobs),
            "total_findings": len(findings),
            "by_severity": by_severity,
        },
        "jobs": [
            {
                "id": str(job.id),
                "tool": job.tool,
                "target": job.target,
                "status": job.status.value,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "exit_code": job.exit_code,
                "ai_analysis": job.ai_analysis,
                "evidence_sha256": job.evidence_sha256,
            }
            for job in jobs
        ],
        "findings": [
            {
                "id": str(f.id),
                "job_id": str(f.job_id),
                "target": f.target,
                "source_tool": f.source_tool,
                "title": f.title,
                "description": f.description,
                "severity": f.severity.value,
                "confidence": f.confidence.value,
                "evidence": f.evidence,
                "recommendation": f.recommendation,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in findings
        ],
    }
