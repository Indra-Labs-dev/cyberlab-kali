"""Phase 19 -- Summary Agent (AI Memory per Project). Writes a short
natural-language summary of a Project's current state from already-loaded
data (assets, a severity breakdown, recent AssetChangeEvent rows) --
never queries the DB itself, never writes anything. Persistence
(ProjectAISummary upsert) happens exclusively in app/ai/memory.py, which
calls this agent and then does the write, mirroring the read-only-agent /
stateful-service split already established by CorrelationAgent+the
accept route (Phase 18) and ReportAgent+POST /api/reports.

Unlike CorrelationSuggestion/ReportProposal, a summary carries no ids for
the model to hallucinate -- it's free text, not a structured proposal --
so there is no id-revalidation step here, just length capping.
"""

from app.ai.prompts import SUMMARY_SYSTEM, build_summary_prompt
from app.ai.provider import AIProvider
from app.models.asset import Asset
from app.models.asset_change_event import AssetChangeEvent

_MAX_SUMMARY_LENGTH = 2000


def _asset_summary(asset: Asset) -> dict:
    return {
        "name": asset.name,
        "address": asset.address,
        "criticality": asset.criticality.value,
        "authorization_status": asset.authorization_status.value,
    }


def _change_summary(change: AssetChangeEvent) -> dict:
    return {
        "change_type": change.change_type.value,
        "field": change.field,
        "old_value": change.old_value,
        "new_value": change.new_value,
        "detected_at": change.detected_at.isoformat() if change.detected_at else None,
    }


class SummaryAgent:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def summarize(
        self,
        project_name: str,
        assets: list[Asset],
        severity_counts: dict[str, int],
        recent_changes: list[AssetChangeEvent],
    ) -> str:
        if not assets:
            return f"{project_name} has no tracked assets yet."

        prompt = build_summary_prompt(
            project_name,
            [_asset_summary(a) for a in assets],
            severity_counts,
            [_change_summary(c) for c in recent_changes],
        )
        raw = await self.provider.generate(prompt, system=SUMMARY_SYSTEM, json_mode=False)
        text = raw.strip()
        if not text:
            return f"{project_name}: {len(assets)} asset(s) tracked, no summary available."
        return text[:_MAX_SUMMARY_LENGTH]
