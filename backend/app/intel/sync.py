"""Background ingestion orchestration -- the only place that calls out to
EPSS/CISA KEV/NVD. Runs from a thread in cyberlab-worker (see
app/jobs/worker.py) and from the manual `POST /api/intelligence/sync`
trigger (enqueued through RQ, see app/api/routes/intelligence.py) -- never
from a request handler directly, and never blocking a Finding/Asset read.

Each source's failure is isolated: EPSS being down must never prevent CISA
KEV from syncing, and neither ever crashes the calling thread -- see
run_full_sync().
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.sync_session import get_sync_session
from app.intel.cisa_kev import CisaKevFetchError, fetch_cisa_kev_catalog
from app.intel.epss import EPSSFetchError, fetch_epss_scores
from app.intel.nvd import NVDFetchError, fetch_nvd_cvss
from app.models.finding import Finding
from app.models.vulnerability_intel import CisaKevEntry, IntelSyncState, VulnerabilityIntel
from app.risk.service import recalculate_all_findings_with_cve, recalculate_findings_for_cve

logger = logging.getLogger("cyberlab.intel")

# NVD's unauthenticated rate limit is ~5 requests per rolling 30s window --
# comfortably respected with a fixed gap between calls rather than a more
# complex token-bucket for what is, in practice, a handful of CVEs per run.
NVD_MIN_INTERVAL_SECONDS = 6.5
NVD_MAX_CVES_PER_RUN = 20

# EPSS values are republished daily by FIRST -- re-fetching more often than
# this would just return the same number.
EPSS_REFRESH_INTERVAL = timedelta(hours=20)


def known_cve_ids(session: Session) -> set[str]:
    """Every CVE CyberLab has actually seen in a Finding -- the scope for
    EPSS/NVD ingestion (never a bulk catalog download, see
    docs/phase-15-risk-score.md)."""
    cve_ids: set[str] = set()
    for row in session.execute(select(Finding.cve_ids)).scalars():
        cve_ids.update(row or [])
    return cve_ids


def _get_or_create_state(session: Session, source: str) -> IntelSyncState:
    state = session.get(IntelSyncState, source)
    if state is None:
        state = IntelSyncState(source=source)
        session.add(state)
    return state


def _record_attempt(session: Session, source: str) -> None:
    state = _get_or_create_state(session, source)
    state.last_attempt_at = datetime.now(timezone.utc)
    session.commit()


def _record_success(session: Session, source: str, details: dict) -> None:
    state = _get_or_create_state(session, source)
    state.last_success_at = datetime.now(timezone.utc)
    state.last_error = None
    state.details = details
    session.commit()


def _record_failure(session: Session, source: str, error: object) -> None:
    state = _get_or_create_state(session, source)
    state.last_error = str(error)[:2000]
    session.commit()
    logger.warning("intel sync %r failed: %s", source, error)


def sync_epss(session: Session | None = None) -> None:
    owns_session = session is None
    session = session or get_sync_session()
    try:
        _record_attempt(session, "epss")
        cves = sorted(known_cve_ids(session))
        if not cves:
            _record_success(session, "epss", {"cves_checked": 0})
            return

        try:
            scores = fetch_epss_scores(cves)
        except EPSSFetchError as exc:
            _record_failure(session, "epss", exc)
            return

        now = datetime.now(timezone.utc)
        for cve in cves:
            intel = session.get(VulnerabilityIntel, cve)
            if intel is None:
                intel = VulnerabilityIntel(cve=cve)
                session.add(intel)
            data = scores.get(cve)
            if data is not None:
                intel.epss_score = data["epss"]
                intel.epss_percentile = data["percentile"]
            intel.epss_fetched_at = now
        session.commit()

        for cve in cves:
            recalculate_findings_for_cve(session, cve)
        session.commit()

        _record_success(session, "epss", {"cves_checked": len(cves), "cves_with_data": len(scores)})
    finally:
        if owns_session:
            session.close()


def sync_cisa_kev(session: Session | None = None) -> None:
    owns_session = session is None
    session = session or get_sync_session()
    try:
        _record_attempt(session, "cisa_kev")
        try:
            entries = fetch_cisa_kev_catalog()
        except CisaKevFetchError as exc:
            _record_failure(session, "cisa_kev", exc)
            return

        existing = {row.cve_id: row for row in session.execute(select(CisaKevEntry)).scalars()}
        seen: set[str] = set()
        now = datetime.now(timezone.utc)
        for entry in entries:
            seen.add(entry["cve_id"])
            row = existing.get(entry["cve_id"])
            if row is None:
                row = CisaKevEntry(cve_id=entry["cve_id"])
                session.add(row)
            row.vendor_project = entry["vendor_project"]
            row.product = entry["product"]
            row.vulnerability_name = entry["vulnerability_name"]
            row.date_added = entry["date_added"]
            row.due_date = entry["due_date"]
            row.known_ransomware_campaign_use = entry["known_ransomware_campaign_use"]
            row.fetched_at = now
        for cve_id, row in existing.items():
            if cve_id not in seen:
                session.delete(row)
        session.commit()

        _record_success(session, "cisa_kev", {"catalog_size": len(entries)})

        # KEV membership can change for any CVE at once -- recompute every
        # finding that has a CVE (bounded, no network calls per finding).
        recalculate_all_findings_with_cve(session)
        session.commit()
    finally:
        if owns_session:
            session.close()


def sync_nvd_cvss(session: Session | None = None, max_cves: int = NVD_MAX_CVES_PER_RUN) -> None:
    owns_session = session is None
    session = session or get_sync_session()
    try:
        _record_attempt(session, "nvd")

        known = known_cve_ids(session)
        have_cvss = {
            row.cve
            for row in session.execute(select(VulnerabilityIntel).where(VulnerabilityIntel.cvss_score.isnot(None))).scalars()
        }
        missing = sorted(known - have_cvss)[:max_cves]

        if not missing:
            _record_success(session, "nvd", {"cves_checked": 0})
            return

        updated: list[str] = []
        errors: list[str] = []
        for i, cve in enumerate(missing):
            if i > 0:
                time.sleep(NVD_MIN_INTERVAL_SECONDS)
            try:
                result = fetch_nvd_cvss(cve)
            except NVDFetchError as exc:
                errors.append(str(exc))
                continue

            intel = session.get(VulnerabilityIntel, cve)
            if intel is None:
                intel = VulnerabilityIntel(cve=cve)
                session.add(intel)
            intel.cvss_fetched_at = datetime.now(timezone.utc)
            if result is not None:
                intel.cvss_score = result["score"]
                intel.cvss_version = result["version"]
                intel.cvss_vector = result["vector"]
                intel.cvss_source = "nvd"
            updated.append(cve)
        session.commit()

        for cve in updated:
            recalculate_findings_for_cve(session, cve)
        session.commit()

        if errors and not updated:
            _record_failure(session, "nvd", "; ".join(errors[:5]))
        else:
            _record_success(session, "nvd", {"cves_checked": len(missing), "errors": len(errors)})
    finally:
        if owns_session:
            session.close()


def run_full_sync() -> None:
    """Runs all three sources back to back in one session. Entry point for
    both the periodic background thread (app/jobs/worker.py) and the manual
    `POST /api/intelligence/sync` trigger. Each source's exception is caught
    individually -- see module docstring."""
    session = get_sync_session()
    try:
        for name, fn in (("cisa_kev", sync_cisa_kev), ("epss", sync_epss), ("nvd", sync_nvd_cvss)):
            try:
                fn(session)
            except Exception:
                logger.exception("intel sync %r crashed unexpectedly", name)
    finally:
        session.close()


def start_intel_sync_thread(poll_interval_seconds: int) -> threading.Thread:
    """Starts the periodic sync loop as a daemon thread -- called once from
    app/jobs/worker.py, alongside the Phase 14 scheduler ticker. A distinct
    thread rather than reusing ScheduledJob/the Continuous Recon ticker: that
    model is specifically "run a Kali tool against an Asset" (asset_id,
    tool, profile, Policy Engine authorization) and intelligence sync is
    none of those things -- forcing it through ScheduledJob would mean a
    fake asset_id and a ticker re-checking authorization that doesn't apply
    here. Reusing the *pattern* (background thread in the existing worker
    process, Postgres-tracked state) without reusing the *model* is the
    deliberate choice, see docs/phase-15-risk-score.md.
    """

    def _loop() -> None:
        logger.info("intel sync thread started (poll interval: %ss)", poll_interval_seconds)
        while True:
            try:
                run_full_sync()
            except Exception:  # noqa: BLE001 -- one bad cycle must not kill the loop
                logger.exception("intel sync cycle failed")
            time.sleep(poll_interval_seconds)

    thread = threading.Thread(target=_loop, name="intel-sync", daemon=True)
    thread.start()
    return thread
