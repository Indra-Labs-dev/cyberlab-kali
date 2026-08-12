"""Phase 16 -- deduplication/merge, wired into app/jobs/tasks.py::execute_job
in place of the old unconditional `Finding(job_id=job.id, **finding_data)`
insert loop. Sync-only (same app/db/sync_session.py pattern as the rest of
the worker-side code).

Concurrency: relies on PostgreSQL itself (`SELECT ... FOR UPDATE` plus the
partial unique index on `signature`), not an application-level lock. Two
sessions racing to create the *first* observation of a brand new signature
both attempt an INSERT; the second one loses to the unique constraint and
retries -- at which point its SELECT ... FOR UPDATE finds the row the first
session just committed and merges into it instead. The failed INSERT is
isolated in a SAVEPOINT (`session.begin_nested()`) so retrying never rolls
back the rest of the enclosing execute_job() transaction (job status,
other findings, asset activity, Diff Engine, Risk Score). See
docs/phase-16-correlation-deduplication.md and
tests/findings/test_concurrency.py for the real-Postgres proof.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.findings.lifecycle import maybe_auto_reopen
from app.findings.signature import extract_port_protocol, finding_signature, normalize_title
from app.models.finding import Finding
from app.models.job import Job
from app.risk.service import recalculate_finding_risk

_MAX_UPSERT_ATTEMPTS = 5


def upsert_finding(session: Session, job: Job, finding_data: dict) -> Finding:
    """Creates a new Finding, or merges `finding_data` into the existing one
    sharing its signature. Never creates a duplicate for the same logical
    finding. Does not commit -- callers (execute_job) own the transaction.
    """
    source_tool = finding_data["source_tool"]
    title = finding_data["title"]
    target = finding_data["target"]
    evidence = finding_data.get("evidence") or {}
    cve_ids = sorted({c.upper() for c in finding_data.get("cve_ids") or [] if c})

    normalized_title = normalize_title(title)
    port, protocol = extract_port_protocol(source_tool, target, evidence)
    signature = finding_signature(job.target_id, cve_ids, normalized_title, port, protocol)
    observed_at = job.finished_at or datetime.now(timezone.utc)

    if signature is None:
        # No Asset on this job -- no identity to dedup against, same
        # behavior as every phase before Phase 16 for free-text-target jobs.
        finding = _build_finding(job, finding_data, cve_ids, signature=None, observed_at=observed_at)
        session.add(finding)
        session.flush()  # populate column defaults (e.g. confidence) before risk inputs read them
        recalculate_finding_risk(session, finding)
        return finding

    for _ in range(_MAX_UPSERT_ATTEMPTS):
        existing = session.execute(
            select(Finding).where(Finding.signature == signature).with_for_update()
        ).scalar_one_or_none()

        if existing is not None:
            _merge_observation(session, existing, job, finding_data, cve_ids, observed_at)
            return existing

        finding = _build_finding(job, finding_data, cve_ids, signature=signature, observed_at=observed_at)
        try:
            with session.begin_nested():
                session.add(finding)
                session.flush()
        except IntegrityError:
            # Another session committed the same signature between our
            # SELECT and our INSERT -- the SAVEPOINT above is already rolled
            # back, which also already detaches `finding` from the session
            # (ROLLBACK TO SAVEPOINT discards everything added within it) --
            # expunging an already-detached instance raises InvalidRequestError,
            # so only do it if it's still actually attached. Loop again, this
            # time the SELECT ... FOR UPDATE will find (and block briefly on,
            # then see) the row the other session committed.
            if finding in session:
                session.expunge(finding)
            continue

        recalculate_finding_risk(session, finding)
        return finding

    raise RuntimeError(f"could not upsert finding (signature={signature}) after {_MAX_UPSERT_ATTEMPTS} attempts")


def _build_finding(job: Job, finding_data: dict, cve_ids: list[str], *, signature: str | None, observed_at: datetime) -> Finding:
    source_tool = finding_data["source_tool"]
    return Finding(
        job_id=job.id,
        target=finding_data["target"],
        source_tool=source_tool,
        title=finding_data["title"],
        description=finding_data["description"],
        severity=finding_data["severity"],
        evidence=finding_data.get("evidence") or {},
        recommendation=finding_data.get("recommendation"),
        cve_ids=cve_ids,
        signature=signature,
        first_seen=observed_at,
        last_seen=observed_at,
        observation_count=1,
        source_tools=[source_tool],
        observation_job_ids=[str(job.id)],
    )


def _merge_observation(
    session: Session,
    finding: Finding,
    job: Job,
    finding_data: dict,
    cve_ids: list[str],
    observed_at: datetime,
) -> None:
    source_tool = finding_data["source_tool"]

    # first_seen is the earliest known observation, last_seen the latest --
    # neither ever moves in the wrong direction, regardless of the order
    # jobs happen to finish in.
    if observed_at < finding.first_seen:
        finding.first_seen = observed_at
    if observed_at > finding.last_seen:
        finding.last_seen = observed_at

    finding.observation_count += 1

    if source_tool not in finding.source_tools:
        finding.source_tools = [*finding.source_tools, source_tool]

    job_id_str = str(job.id)
    if job_id_str not in finding.observation_job_ids:
        finding.observation_job_ids = [*finding.observation_job_ids, job_id_str]

    # Union, never lose a previously-known CVE (a later/duller observation
    # missing a CVE the first one had must not erase it).
    merged_cve_ids = sorted(set(finding.cve_ids) | set(cve_ids))
    cve_ids_changed = merged_cve_ids != finding.cve_ids
    if cve_ids_changed:
        finding.cve_ids = merged_cve_ids

    # A known value is never replaced by an unknown one.
    new_recommendation = finding_data.get("recommendation")
    if new_recommendation:
        finding.recommendation = new_recommendation

    new_description = finding_data.get("description")
    if new_description:
        finding.description = new_description

    # Latest raw evidence wins -- superseded evidence remains reachable via
    # the contributing Job rows themselves (observation_job_ids), never
    # deleted, matching "ne supprime jamais les résultats bruts des Jobs".
    finding.evidence = finding_data.get("evidence") or finding.evidence

    maybe_auto_reopen(
        session,
        finding,
        reason=f"Re-observed by {source_tool} (job {job.id})",
    )

    # Risk Score depends on cve_ids (-> CVSS/EPSS/KEV lookups) and
    # confidence/severity, neither of which changed here unless cve_ids
    # did -- recompute only when it's actually worth it.
    if cve_ids_changed:
        recalculate_finding_risk(session, finding)
