"""Phase 18.8 -- Correlation Agent. Proposes possible links between
existing Findings that Phase 16's fixed deterministic rules
(app/findings/correlation.py) don't catch -- an LLM's judgment on
non-obvious signal (e.g. "outdated jQuery" + "reflected XSS" plausibly
related), never a replacement for the deterministic engine, which keeps
running unchanged and untouched by this phase.

Read-only by construction, like AIAnalyst/AIMissionPlanner before it: this
class only ever receives already-loaded data (a list of Finding rows, an
optional list of graph-context strings) as plain arguments -- it never
imports a Session, never queries the DB itself, and returns pydantic
CorrelationSuggestion objects, never a FindingRelation or an
AICorrelationSuggestion. Persisting a suggestion as PENDING, and turning an
accepted one into a real FindingRelation, both happen only in
app/api/routes/ai.py -- never here.
"""

from app.ai.parsing import extract_json
from app.ai.prompts import CORRELATION_SYSTEM, build_correlation_prompt
from app.ai.provider import AIProvider
from app.ai.schemas import CorrelationSuggestion
from app.models.finding import Finding


def _finding_summary(finding: Finding) -> dict:
    evidence = finding.evidence if isinstance(finding.evidence, dict) else {}
    return {
        "id": str(finding.id),
        "tool": finding.source_tool,
        "title": finding.title,
        "severity": finding.severity.value,
        "cve_ids": finding.cve_ids,
        "port": evidence.get("port"),
        "service": evidence.get("service"),
    }


class CorrelationAgent:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def suggest(
        self, findings: list[Finding], graph_context: list[str] | None = None
    ) -> list[CorrelationSuggestion]:
        if len(findings) < 2:
            return []

        prompt = build_correlation_prompt([_finding_summary(f) for f in findings], graph_context)
        raw = await self.provider.generate(prompt, system=CORRELATION_SYSTEM, json_mode=True)

        data = extract_json(raw)
        if data is None or "suggestions" not in data:
            return []

        # Never trust an id the model output: only ids from the exact
        # Finding set the caller passed in are ever accepted, the same
        # re-validation shape AIMissionPlanner uses for tool names.
        valid_ids = {f.id for f in findings}
        suggestions: list[CorrelationSuggestion] = []
        for raw_item in data.get("suggestions", []):
            try:
                item = CorrelationSuggestion.model_validate(raw_item)
            except Exception:
                continue
            if item.finding_id not in valid_ids or item.related_finding_id not in valid_ids:
                continue
            if item.finding_id == item.related_finding_id:
                continue
            suggestions.append(item)
        return suggestions
