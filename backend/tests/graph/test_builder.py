import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import and_, or_, select

from app.db.sync_session import get_sync_session
from app.graph.builder import build_graph_for_asset, delete_edges_for_finding
from app.main import app
from app.models.finding import Finding
from app.models.graph_edge import GraphEdge
from app.models.job import Job, JobStatus


async def _make_asset(technologies: list[str] | None = None, project_id: str | None = None) -> tuple[str, str]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        if project_id is None:
            project = (await ac.post("/api/projects", json={"name": "Graph Builder Fixture"})).json()
            project_id = project["id"]
        asset = (
            await ac.post(
                f"/api/projects/{project_id}/assets",
                json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()
    if technologies:
        session = get_sync_session()
        try:
            from app.models.asset import Asset

            db_asset = session.get(Asset, uuid.UUID(asset["id"]))
            db_asset.technologies = technologies
            session.commit()
        finally:
            session.close()
    return project_id, asset["id"]


def _make_finding(asset_id: str, source_tool: str = "nmap", evidence: dict | None = None, cve_ids: list[str] | None = None) -> Finding:
    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool=source_tool, target="x", target_id=uuid.UUID(asset_id), params={}, status=JobStatus.SUCCESS)
        session.add(job)
        session.commit()

        finding = Finding(
            job_id=job.id,
            target="x",
            source_tool=source_tool,
            title=f"{source_tool} finding",
            description="",
            severity="INFO",
            evidence=evidence or {},
            cve_ids=cve_ids or [],
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)
        return finding
    finally:
        session.close()


def _edges_for(session, from_type: str, from_id: str) -> list[GraphEdge]:
    return list(
        session.execute(select(GraphEdge).where(GraphEdge.from_type == from_type, GraphEdge.from_id == from_id)).scalars()
    )


async def test_build_graph_creates_has_finding_edge():
    _, asset_id = await _make_asset()
    finding = _make_finding(asset_id)

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()

        edges = _edges_for(session, "ASSET", asset_id)
        has_finding = [e for e in edges if e.relation == "HAS_FINDING" and e.to_id == str(finding.id)]
        assert len(has_finding) == 1
        assert has_finding[0].source == "system"
    finally:
        session.close()


async def test_build_graph_creates_exposes_for_nmap_open_port():
    _, asset_id = await _make_asset()
    _make_finding(asset_id, source_tool="nmap", evidence={"port": 80, "protocol": "tcp", "state": "open", "service": "http"})

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()

        edges = _edges_for(session, "ASSET", asset_id)
        exposes = [e for e in edges if e.relation == "EXPOSES"]
        assert len(exposes) == 1
        assert exposes[0].to_type == "SERVICE"
        assert exposes[0].to_id == "80/tcp"
        assert exposes[0].edge_metadata["service"] == "http"
    finally:
        session.close()


async def test_build_graph_never_exposes_service_for_whatweb():
    # whatweb observes an application, never a confirmed open port -- must
    # never produce an EXPOSES edge, only nmap/masscan can.
    _, asset_id = await _make_asset()
    _make_finding(asset_id, source_tool="whatweb", evidence={"plugin": "Apache"})

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()

        edges = _edges_for(session, "ASSET", asset_id)
        assert [e for e in edges if e.relation == "EXPOSES"] == []
    finally:
        session.close()


async def test_build_graph_creates_uses_technology_from_asset_technologies():
    _, asset_id = await _make_asset(technologies=["Apache", "PHP"])

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()

        edges = _edges_for(session, "ASSET", asset_id)
        tech_edges = {e.to_id for e in edges if e.relation == "USES_TECHNOLOGY"}
        assert tech_edges == {"Apache", "PHP"}
    finally:
        session.close()


async def test_build_graph_creates_references_cve_from_finding_cve_ids():
    _, asset_id = await _make_asset()
    finding = _make_finding(asset_id, source_tool="nuclei", cve_ids=["CVE-2021-44228"])

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()

        edges = _edges_for(session, "FINDING", str(finding.id))
        cve_edges = [e for e in edges if e.relation == "REFERENCES_CVE"]
        assert len(cve_edges) == 1
        assert cve_edges[0].to_type == "CVE"
        assert cve_edges[0].to_id == "CVE-2021-44228"
    finally:
        session.close()


async def test_build_graph_mirrors_finding_relation_as_related_to():
    _, asset_id = await _make_asset()
    nmap_f = _make_finding(asset_id, source_tool="nmap", evidence={"port": 80, "protocol": "tcp", "state": "open", "service": "http"})
    whatweb_f = _make_finding(asset_id, source_tool="whatweb", evidence={"plugin": "Apache"})

    session = get_sync_session()
    try:
        from app.models.finding_relation import FindingRelation

        session.add(
            FindingRelation(
                finding_id=nmap_f.id,
                related_finding_id=whatweb_f.id,
                rule="RULE_NMAP_WHATWEB_PORT",
                reason="nmap and whatweb agree on port 80.",
            )
        )
        session.commit()

        from app.models.asset import Asset

        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()

        edges = _edges_for(session, "FINDING", str(nmap_f.id))
        related = [e for e in edges if e.relation == "RELATED_TO"]
        assert len(related) == 1
        assert related[0].to_id == str(whatweb_f.id)
        assert related[0].source == "phase16_correlation"
    finally:
        session.close()


async def test_build_graph_links_assets_sharing_a_technology_same_project():
    project_id, asset_a = await _make_asset(technologies=["Apache"])
    _, asset_b = await _make_asset(technologies=["Apache", "PHP"], project_id=project_id)

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        a = session.get(Asset, uuid.UUID(asset_a))
        b = session.get(Asset, uuid.UUID(asset_b))
        build_graph_for_asset(session, a)
        build_graph_for_asset(session, b)
        session.commit()

        all_related = session.execute(
            select(GraphEdge).where(GraphEdge.from_type == "ASSET", GraphEdge.to_type == "ASSET", GraphEdge.relation == "RELATED_TO")
        ).scalars().all()
        matching = [e for e in all_related if {e.from_id, e.to_id} == {asset_a, asset_b}]
        assert len(matching) == 1
        assert matching[0].edge_metadata["shared_technologies"] == ["Apache"]
    finally:
        session.close()


async def test_build_graph_never_links_assets_across_different_projects():
    _, asset_a = await _make_asset(technologies=["Apache"])
    _, asset_b = await _make_asset(technologies=["Apache"])  # different project (default fixture creates a new one)

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        a = session.get(Asset, uuid.UUID(asset_a))
        b = session.get(Asset, uuid.UUID(asset_b))
        build_graph_for_asset(session, a)
        build_graph_for_asset(session, b)
        session.commit()

        all_related = session.execute(
            select(GraphEdge).where(GraphEdge.from_type == "ASSET", GraphEdge.to_type == "ASSET", GraphEdge.relation == "RELATED_TO")
        ).scalars().all()
        matching = [e for e in all_related if {e.from_id, e.to_id} == {asset_a, asset_b}]
        assert matching == []
    finally:
        session.close()


async def test_build_graph_is_idempotent():
    _, asset_id = await _make_asset(technologies=["Apache"])
    _make_finding(asset_id, source_tool="nmap", evidence={"port": 80, "protocol": "tcp", "state": "open", "service": "http"})

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()
        first_count = len(_edges_for(session, "ASSET", asset_id))

        build_graph_for_asset(session, asset)
        session.commit()
        second_count = len(_edges_for(session, "ASSET", asset_id))

        assert first_count == second_count
        assert first_count > 0
    finally:
        session.close()


async def test_delete_edges_for_finding_removes_related_edges():
    _, asset_id = await _make_asset()
    finding = _make_finding(asset_id, source_tool="nuclei", cve_ids=["CVE-2021-44228"])

    session = get_sync_session()
    try:
        from app.models.asset import Asset

        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()
        assert len(_edges_for(session, "FINDING", str(finding.id))) > 0

        delete_edges_for_finding(session, finding.id)
        session.commit()

        remaining = session.execute(
            select(GraphEdge).where(
                or_(
                    and_(GraphEdge.from_type == "FINDING", GraphEdge.from_id == str(finding.id)),
                    and_(GraphEdge.to_type == "FINDING", GraphEdge.to_id == str(finding.id)),
                )
            )
        ).scalars().all()
        assert remaining == []
    finally:
        session.close()
