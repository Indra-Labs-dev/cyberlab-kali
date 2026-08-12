"""DB-aware glue between Finding/Asset/VulnerabilityIntel and the pure
app/risk/calculator.py. Sync-only (same app/db/sync_session.py pattern as
the rest of the worker-side code: app/jobs/tasks.py, app/diff/service.py,
app/scheduling/ticker.py) -- the one async caller (PATCH /api/assets/{id}
when criticality changes) dispatches into this module via
`asyncio.to_thread`, see app/api/routes/assets.py.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.sync_session import get_sync_session
from app.models.asset import Asset
from app.models.finding import Confidence, Finding, Severity
from app.models.job import Job
from app.models.vulnerability_intel import CisaKevEntry, IntelSyncState, VulnerabilityIntel
from app.risk.calculator import RiskInputs, RiskResult, calculate_risk


def seed_cvss_from_tool(session: Session, hints: list[dict]) -> set[str]:
    """Upserts vulnerability_intel from CVSS a tool already told us (today:
    nuclei's template classification, see
    app/tools/parsers/nuclei.py::cvss_hints). Never overwrites an existing
    value -- first one in wins, whether that's an earlier nuclei run or a
    prior NVD enrichment; app/intel/sync.py::sync_nvd_cvss only ever queries
    NVD for CVEs still missing a score, so this ordering is what makes
    "reuse the CVSS we already have" actually mean something.
    """
    updated: set[str] = set()
    now = datetime.now(timezone.utc)
    for hint in hints:
        cve = hint["cve"]
        intel = session.get(VulnerabilityIntel, cve)
        if intel is None:
            intel = VulnerabilityIntel(cve=cve)
            session.add(intel)
        if intel.cvss_score is None:
            intel.cvss_score = hint["cvss_score"]
            intel.cvss_version = hint["cvss_version"]
            intel.cvss_vector = hint["cvss_vector"]
            intel.cvss_source = "nuclei_template"
            intel.cvss_fetched_at = now
            updated.add(cve)
    return updated


def build_risk_inputs(session: Session, finding: Finding) -> RiskInputs:
    cvss_score = cvss_version = epss_score = epss_percentile = None
    kev: bool | None = None

    if finding.cve_ids:
        intel_rows = list(
            session.execute(select(VulnerabilityIntel).where(VulnerabilityIntel.cve.in_(finding.cve_ids))).scalars()
        )

        # A finding can (rarely) match multiple CVEs -- conservative choice:
        # use whichever CVE scores worst, never average away the risk.
        cvss_rows = [r for r in intel_rows if r.cvss_score is not None]
        if cvss_rows:
            best_cvss = max(cvss_rows, key=lambda r: r.cvss_score)
            cvss_score, cvss_version = best_cvss.cvss_score, best_cvss.cvss_version

        epss_rows = [r for r in intel_rows if r.epss_score is not None]
        if epss_rows:
            best_epss = max(epss_rows, key=lambda r: r.epss_score)
            epss_score, epss_percentile = best_epss.epss_score, best_epss.epss_percentile

        # KEV is YES/NO only once the catalog has synced successfully at
        # least once -- otherwise every lookup is honestly UNKNOWN, never
        # guessed as "not listed".
        kev_state = session.get(IntelSyncState, "cisa_kev")
        if kev_state is not None and kev_state.last_success_at is not None:
            matched = session.execute(
                select(CisaKevEntry.cve_id).where(CisaKevEntry.cve_id.in_(finding.cve_ids))
            ).scalars().all()
            kev = len(matched) > 0

    asset_criticality = None
    job = session.get(Job, finding.job_id)
    if job is not None and job.target_id is not None:
        asset = session.get(Asset, job.target_id)
        if asset is not None:
            asset_criticality = asset.criticality

    return RiskInputs(
        # Finding.severity/confidence can still be plain strings in memory
        # right after `Finding(...)` construction (SQLAlchemy only coerces
        # an Enum column to the Python enum member on a DB round-trip, not
        # on attribute assignment) -- recalculate_finding_risk is called on
        # a just-built, not-yet-flushed Finding in app/jobs/tasks.py, so
        # this normalization is not optional.
        severity=finding.severity if isinstance(finding.severity, Severity) else Severity(finding.severity),
        confidence=finding.confidence if isinstance(finding.confidence, Confidence) else Confidence(finding.confidence),
        cvss_score=cvss_score,
        cvss_version=cvss_version,
        epss_score=epss_score,
        epss_percentile=epss_percentile,
        kev=kev,
        asset_criticality=asset_criticality,
    )


def recalculate_finding_risk(session: Session, finding: Finding) -> RiskResult:
    """Computes and writes the materialized cache columns on `finding`
    (cvss_score/epss_score/kev/risk_score/risk_priority/risk_calculated_at).
    Does not commit -- callers own the transaction (this is called in tight
    loops during sync)."""
    inputs = build_risk_inputs(session, finding)
    result = calculate_risk(inputs)
    finding.cvss_score = inputs.cvss_score
    finding.epss_score = inputs.epss_score
    finding.kev = inputs.kev
    finding.risk_score = result.score
    finding.risk_priority = result.priority
    finding.risk_calculated_at = datetime.now(timezone.utc)
    return result


def _findings_with_any_cve(session: Session) -> list[Finding]:
    # Bounded local-tool scale (see docs/phase-15-risk-score.md performance
    # notes) -- loading all findings and filtering in Python is simpler and
    # fast enough than a JSON-containment SQL predicate, and avoids a
    # Postgres-JSON-operator dependency for a few hundred rows at most.
    return [f for f in session.execute(select(Finding)).scalars() if f.cve_ids]


def recalculate_findings_for_cve(session: Session, cve: str) -> list[Finding]:
    updated = [f for f in _findings_with_any_cve(session) if cve in f.cve_ids]
    for finding in updated:
        recalculate_finding_risk(session, finding)
    return updated


def recalculate_all_findings_with_cve(session: Session) -> list[Finding]:
    """Used after a CISA KEV catalog sync: KEV membership can change for any
    of the CVEs CyberLab knows about at once, so every finding that has a
    CVE is worth recomputing -- still a bounded, CPU-only pass, no network
    calls per finding."""
    updated = _findings_with_any_cve(session)
    for finding in updated:
        recalculate_finding_risk(session, finding)
    return updated


def recalculate_findings_for_asset(session: Session, asset_id: UUID) -> list[Finding]:
    job_ids = session.execute(select(Job.id).where(Job.target_id == asset_id)).scalars().all()
    if not job_ids:
        return []
    findings = list(session.execute(select(Finding).where(Finding.job_id.in_(job_ids))).scalars())
    for finding in findings:
        recalculate_finding_risk(session, finding)
    return findings


def recalculate_findings_for_asset_sync(asset_id: UUID) -> int:
    """Self-contained wrapper (own session, commits, closes) for callers
    outside the worker's sync-session-per-request patterns -- specifically
    `PATCH /api/assets/{id}` (async route) dispatching via
    `asyncio.to_thread` when criticality changes, see
    app/api/routes/assets.py. Returns how many Findings were recomputed.
    """
    session = get_sync_session()
    try:
        findings = recalculate_findings_for_asset(session, asset_id)
        session.commit()
        return len(findings)
    finally:
        session.close()
