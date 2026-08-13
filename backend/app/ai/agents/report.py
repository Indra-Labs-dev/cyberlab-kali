"""Phase 18.9 -- Report Agent. Proposes what a report could cover -- a
title and which completed Jobs to include -- for a human to review and
edit. It never generates a report itself: the mandatory pattern is
ReportAgent -> ReportProposal -> human validation/edit -> POST /api/reports
-> real generation (app/reports/*, app/api/routes/reports.py -- both
completely untouched by this phase). This class never imports
build_report_data/render, never imports the Report model, and never
touches a DB write session -- read-only, like every other agent in
app/ai/agents/.
"""

from app.ai.parsing import extract_json
from app.ai.prompts import REPORT_SYSTEM, build_report_proposal_prompt
from app.ai.provider import AIProvider
from app.ai.schemas import ReportProposal
from app.models.job import Job


def _job_summary(job: Job) -> dict:
    return {
        "id": str(job.id),
        "tool": job.tool,
        "target": job.target,
        "status": job.status.value,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


class ReportAgent:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def propose(self, project_name: str, jobs: list[Job]) -> ReportProposal:
        if not jobs:
            return ReportProposal(title=f"{project_name} report", job_ids=[], rationale="No completed jobs yet.")

        prompt = build_report_proposal_prompt(project_name, [_job_summary(j) for j in jobs])
        raw = await self.provider.generate(prompt, system=REPORT_SYSTEM, json_mode=True)

        data = extract_json(raw)
        valid_ids = {j.id for j in jobs}

        if data is None or "job_ids" not in data:
            # Fall back to proposing every completed job rather than an
            # empty, unusable proposal -- still just a proposal, the human
            # edits it before anything is generated.
            return ReportProposal(
                title=f"{project_name} report",
                job_ids=[j.id for j in jobs],
                rationale="AI proposal could not be parsed; defaulted to all completed jobs.",
            )

        try:
            proposal = ReportProposal.model_validate(data)
        except Exception:
            return ReportProposal(
                title=f"{project_name} report",
                job_ids=[j.id for j in jobs],
                rationale="AI proposal had an unexpected shape; defaulted to all completed jobs.",
            )

        # Never trust a job id the model invented -- same re-validation
        # shape as every other agent's ids.
        proposal.job_ids = [job_id for job_id in proposal.job_ids if job_id in valid_ids]
        if not proposal.title.strip():
            proposal.title = f"{project_name} report"
        return proposal
