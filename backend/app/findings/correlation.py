"""Phase 16 -- cross-tool correlation. Three fixed, explicit rules, not a
generic rule engine: each rule is a small Python function that produces a
human-readable `reason`, never an opaque link. Scoped to the findings of a
single Asset (the one touched by the just-finished job) -- never a global
N-by-N pass over the whole system.

Deliberately separate from deduplication (app/findings/service.py): a
relation links two *distinct* logical Findings that a human should be able
to see are connected, it never merges them into one row. See
docs/phase-16-correlation-deduplication.md for why nmap+whatweb/nuclei stay
separate Findings (their titles never collide, so they'd never dedupe
anyway) while the same CVE from two different tools already merges via
signature (app/findings/signature.py), without needing a relation at all.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.findings.signature import extract_port_protocol
from app.models.finding import Finding
from app.models.finding_relation import FindingRelation
from app.models.job import Job

RULE_NMAP_WHATWEB_PORT = "RULE_NMAP_WHATWEB_PORT"
RULE_NMAP_NUCLEI_PORT = "RULE_NMAP_NUCLEI_PORT"
RULE_SHARED_TECHNOLOGY = "RULE_SHARED_TECHNOLOGY"

# Below this length a substring match on a finding title is too likely to
# be a coincidence (e.g. a 2-character plugin name) -- not a real signal.
_MIN_TECHNOLOGY_LENGTH = 3


def _create_relation_if_new(
    session: Session, finding_a: Finding, finding_b: Finding, rule: str, reason: str, metadata: dict
) -> FindingRelation | None:
    if finding_a.id == finding_b.id:
        return None
    # Canonical ordering (string-compare the UUIDs) so (A,B) and (B,A) are
    # always stored the same way -- the unique constraint on
    # (finding_id, related_finding_id, rule) then guarantees idempotence.
    ordered = sorted((finding_a, finding_b), key=lambda f: str(f.id))
    left, right = ordered[0], ordered[1]

    existing = session.execute(
        select(FindingRelation).where(
            FindingRelation.finding_id == left.id,
            FindingRelation.related_finding_id == right.id,
            FindingRelation.rule == rule,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None

    relation = FindingRelation(
        finding_id=left.id, related_finding_id=right.id, rule=rule, reason=reason, relation_metadata=metadata
    )
    session.add(relation)
    return relation


def _correlate_open_port_with_tool(
    session: Session, findings: list[Finding], other_tool: str, rule: str
) -> list[FindingRelation]:
    nmap_findings = [f for f in findings if f.source_tool == "nmap"]
    other_findings = [f for f in findings if f.source_tool == other_tool]
    if not nmap_findings or not other_findings:
        return []

    created: list[FindingRelation] = []
    for nf in nmap_findings:
        evidence = nf.evidence if isinstance(nf.evidence, dict) else {}
        if evidence.get("state") != "open" or evidence.get("port") is None:
            continue
        port = evidence["port"]
        service = evidence.get("service") or "open"

        for of in other_findings:
            other_port, _ = extract_port_protocol(of.source_tool, of.target, of.evidence)
            if other_port != port:
                continue
            reason = (
                f"nmap identified port {port}/tcp as {service} and {other_tool} observed "
                f'"{of.title}" on the same port.'
            )
            relation = _create_relation_if_new(session, nf, of, rule, reason, {"port": port})
            if relation is not None:
                created.append(relation)
    return created


def _correlate_shared_technology(session: Session, findings: list[Finding]) -> list[FindingRelation]:
    whatweb_findings = [f for f in findings if f.source_tool == "whatweb"]
    other_findings = [f for f in findings if f.source_tool != "whatweb"]
    if not whatweb_findings or not other_findings:
        return []

    created: list[FindingRelation] = []
    for wf in whatweb_findings:
        evidence = wf.evidence if isinstance(wf.evidence, dict) else {}
        technology = evidence.get("plugin")
        if not technology or len(technology) < _MIN_TECHNOLOGY_LENGTH:
            continue
        technology_lower = technology.lower()

        for of in other_findings:
            haystack = f"{of.title} {of.description}".lower()
            if technology_lower not in haystack:
                continue
            reason = (
                f'whatweb identified technology "{technology}", also referenced by '
                f'{of.source_tool}\'s finding "{of.title}".'
            )
            relation = _create_relation_if_new(
                session, wf, of, RULE_SHARED_TECHNOLOGY, reason, {"technology": technology}
            )
            if relation is not None:
                created.append(relation)
    return created


def correlate_asset_findings(session: Session, asset_id) -> list[FindingRelation]:
    """Runs all three rules over every Finding for `asset_id`. Called after
    app/findings/service.py::upsert_finding for a job with a target_id --
    a no-op (empty list) for target_id-less jobs, same precedent as Diff
    Engine/Risk Score.
    """
    if asset_id is None:
        return []

    findings = list(
        session.execute(select(Finding).join(Job, Finding.job_id == Job.id).where(Job.target_id == asset_id)).scalars()
    )
    if len(findings) < 2:
        return []

    created: list[FindingRelation] = []
    created += _correlate_open_port_with_tool(session, findings, "whatweb", RULE_NMAP_WHATWEB_PORT)
    created += _correlate_open_port_with_tool(session, findings, "nuclei", RULE_NMAP_NUCLEI_PORT)
    created += _correlate_shared_technology(session, findings)
    return created
