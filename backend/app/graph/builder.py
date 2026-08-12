"""Phase 17 -- Security Graph builder. Derives graph_edges rows exclusively
from data that already exists elsewhere (Finding.cve_ids, Asset.technologies,
nmap/masscan evidence, Phase 16's FindingRelation) -- never invents an edge
a human couldn't already verify by reading the underlying Finding/Asset.

Idempotent by construction: every edge is upserted via `INSERT ... ON
CONFLICT (from_type, from_id, to_type, to_id, relation) DO UPDATE`, atomic
and race-safe in a single statement. This is simpler than Phase 16's
Finding upsert (SELECT FOR UPDATE + SAVEPOINT retry) on purpose: an edge
carries no accumulated state to merge (no observation_count, no "never
overwrite known with null") -- it's a description of a currently-true fact,
always safe to overwrite wholesale with the latest computation.
"""

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.finding import Finding
from app.models.finding_relation import FindingRelation
from app.models.graph_edge import GraphEdge
from app.models.job import Job

# Tools whose evidence carries a structured, trustworthy port/state --
# same set as app/findings/signature.py::_EVIDENCE_PORT_TOOLS. A SERVICE
# node is only ever created from these two; whatweb/nuclei observe an
# application, not a confirmed open port, so they never produce EXPOSES.
_PORT_SCAN_TOOLS = {"nmap", "masscan"}


def _upsert_edge(
    session: Session,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    relation: str,
    *,
    source: str,
    reason: str,
    metadata: dict | None = None,
) -> None:
    stmt = pg_insert(GraphEdge).values(
        id=uuid.uuid4(),
        from_type=from_type,
        from_id=from_id,
        to_type=to_type,
        to_id=to_id,
        relation=relation,
        source=source,
        reason=reason,
        edge_metadata=metadata or {},
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_graph_edge",
        set_={"source": stmt.excluded.source, "reason": stmt.excluded.reason, "edge_metadata": stmt.excluded.edge_metadata},
    )
    session.execute(stmt)


def _asset_findings(session: Session, asset_id: uuid.UUID) -> list[Finding]:
    return list(
        session.execute(select(Finding).join(Job, Finding.job_id == Job.id).where(Job.target_id == asset_id)).scalars()
    )


def build_graph_for_asset(session: Session, asset: Asset) -> None:
    """(Re)builds every edge derivable from one Asset's current Findings
    and technologies. Safe to call repeatedly (after every job, or from a
    full rebuild) -- never creates a duplicate, always reflects the latest
    known state.
    """
    findings = _asset_findings(session, asset.id)

    for finding in findings:
        _upsert_edge(
            session,
            "ASSET",
            str(asset.id),
            "FINDING",
            str(finding.id),
            "HAS_FINDING",
            source="system",
            reason=f'Finding "{finding.title}" was produced by a job that scanned this asset.',
        )

        evidence = finding.evidence if isinstance(finding.evidence, dict) else {}
        if finding.source_tool in _PORT_SCAN_TOOLS and evidence.get("state") == "open" and evidence.get("port") is not None:
            port = evidence["port"]
            protocol = evidence.get("protocol") or "tcp"
            service_name = evidence.get("service")
            service_id = f"{port}/{protocol}"
            reason = f"{finding.source_tool} observed {service_id} open on this asset" + (
                f", running {service_name}" if service_name else ""
            ) + "."
            _upsert_edge(
                session,
                "ASSET",
                str(asset.id),
                "SERVICE",
                service_id,
                "EXPOSES",
                source=finding.source_tool,
                reason=reason,
                metadata={"port": port, "protocol": protocol, "service": service_name},
            )

        for cve in finding.cve_ids or []:
            _upsert_edge(
                session,
                "FINDING",
                str(finding.id),
                "CVE",
                cve,
                "REFERENCES_CVE",
                source=finding.source_tool,
                reason=f'{finding.source_tool} identified {cve} in finding "{finding.title}".',
            )

    # USES_TECHNOLOGY -- Asset.technologies is already real, observed data
    # (app/assets/activity.py, populated from whatweb plugin names), not
    # re-derived here.
    for tech in asset.technologies or []:
        _upsert_edge(
            session,
            "ASSET",
            str(asset.id),
            "TECHNOLOGY",
            tech,
            "USES_TECHNOLOGY",
            source="whatweb",
            reason=f'whatweb identified "{tech}" on this asset.',
        )

    # RELATED_TO (Finding<->Finding) -- mirrors Phase 16's FindingRelation,
    # never recomputed here (that's app/findings/correlation.py's job).
    finding_ids = {f.id for f in findings}
    if finding_ids:
        relations = session.execute(
            select(FindingRelation).where(
                or_(
                    FindingRelation.finding_id.in_(finding_ids),
                    FindingRelation.related_finding_id.in_(finding_ids),
                )
            )
        ).scalars()
        for rel in relations:
            _upsert_edge(
                session,
                "FINDING",
                str(rel.finding_id),
                "FINDING",
                str(rel.related_finding_id),
                "RELATED_TO",
                source="phase16_correlation",
                reason=rel.reason,
                metadata={"rule": rel.rule},
            )

    # Asset<->Asset RELATED_TO -- the only Asset-Asset relationship
    # honestly derivable from current data: two assets in the same project
    # observed running the same technology. Scoped to one project (not a
    # global N^2 scan) to stay bounded, same precedent as Phase 16
    # correlation being scoped to one asset's findings.
    if asset.technologies:
        siblings = session.execute(
            select(Asset).where(Asset.project_id == asset.project_id, Asset.id != asset.id)
        ).scalars()
        for other in siblings:
            shared = sorted(set(asset.technologies or []) & set(other.technologies or []))
            if not shared:
                continue
            left, right = sorted((asset, other), key=lambda a: str(a.id))
            _upsert_edge(
                session,
                "ASSET",
                str(left.id),
                "ASSET",
                str(right.id),
                "RELATED_TO",
                source="system",
                reason=f"Both assets have been observed running: {', '.join(shared)}.",
                metadata={"shared_technologies": shared},
            )


def delete_edges_for_finding(session: Session, finding_id: uuid.UUID) -> None:
    """Called when a Finding is deleted -- graph_edges has no FK/CASCADE to
    the findings table (FINDING is a logical node type, not every edge
    endpoint has a real foreign key: CVE/SERVICE/TECHNOLOGY are virtual),
    so stale edges must be cleaned up explicitly rather than left dangling.
    """
    finding_id_str = str(finding_id)
    session.query(GraphEdge).filter(
        or_(
            and_(GraphEdge.from_type == "FINDING", GraphEdge.from_id == finding_id_str),
            and_(GraphEdge.to_type == "FINDING", GraphEdge.to_id == finding_id_str),
        )
    ).delete(synchronize_session=False)
