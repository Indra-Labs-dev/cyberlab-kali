import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.sync_session import get_sync_session
from app.findings.correlation import (
    RULE_NMAP_NUCLEI_PORT,
    RULE_NMAP_WHATWEB_PORT,
    RULE_SHARED_TECHNOLOGY,
    correlate_asset_findings,
)
from app.main import app
from app.models.finding import Finding
from app.models.finding_relation import FindingRelation
from app.models.job import Job, JobStatus


async def _make_asset() -> str:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Correlation Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()
    return asset["id"]


def _make_finding(session, asset_id: str, source_tool: str, title: str, target: str, evidence: dict, description: str = "") -> Finding:
    job = Job(id=uuid.uuid4(), tool=source_tool, target=target, target_id=uuid.UUID(asset_id), params={}, status=JobStatus.SUCCESS)
    session.add(job)
    session.commit()

    finding = Finding(
        job_id=job.id,
        target=target,
        source_tool=source_tool,
        title=title,
        description=description,
        severity="INFO",
        evidence=evidence,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)
    return finding


async def test_correlate_nmap_whatweb_same_port_creates_relation():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        nmap_f = _make_finding(
            session, asset_id, "nmap", "Open port 80/tcp (http)", "10.0.0.1",
            {"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
        )
        whatweb_f = _make_finding(
            session, asset_id, "whatweb", "Apache detected", "http://10.0.0.1/",
            {"plugin": "Apache"},
        )

        created = correlate_asset_findings(session, uuid.UUID(asset_id))
        session.commit()

        assert len(created) == 1
        assert created[0].rule == RULE_NMAP_WHATWEB_PORT
        assert "80" in created[0].reason
        assert {created[0].finding_id, created[0].related_finding_id} == {nmap_f.id, whatweb_f.id}
    finally:
        session.close()


async def test_correlate_nmap_nuclei_same_port_creates_relation():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        _make_finding(
            session, asset_id, "nmap", "Open port 443/tcp (https)", "10.0.0.1",
            {"port": 443, "protocol": "tcp", "state": "open", "service": "https"},
        )
        _make_finding(
            session, asset_id, "nuclei", "TLS misconfiguration", "https://10.0.0.1/",
            {"template_id": "tls-misconfig"},
        )

        created = correlate_asset_findings(session, uuid.UUID(asset_id))
        session.commit()

        assert len(created) == 1
        assert created[0].rule == RULE_NMAP_NUCLEI_PORT
    finally:
        session.close()


async def test_correlate_no_relation_when_ports_differ():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        _make_finding(
            session, asset_id, "nmap", "Open port 22/tcp (ssh)", "10.0.0.1",
            {"port": 22, "protocol": "tcp", "state": "open", "service": "ssh"},
        )
        _make_finding(
            session, asset_id, "whatweb", "Apache detected", "http://10.0.0.1/",
            {"plugin": "Apache"},
        )

        created = correlate_asset_findings(session, uuid.UUID(asset_id))
        session.commit()

        assert created == []
    finally:
        session.close()


async def test_correlate_no_relation_when_nmap_port_not_open():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        _make_finding(
            session, asset_id, "nmap", "Closed port 80/tcp", "10.0.0.1",
            {"port": 80, "protocol": "tcp", "state": "closed", "service": "http"},
        )
        _make_finding(
            session, asset_id, "whatweb", "Apache detected", "http://10.0.0.1/",
            {"plugin": "Apache"},
        )

        created = correlate_asset_findings(session, uuid.UUID(asset_id))
        session.commit()

        assert created == []
    finally:
        session.close()


async def test_correlate_shared_technology_matches_title_substring():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        _make_finding(
            session, asset_id, "whatweb", "WordPress detected", "http://10.0.0.1/",
            {"plugin": "WordPress"},
        )
        _make_finding(
            session, asset_id, "nuclei", "WordPress outdated version",
            "http://10.0.0.1/", {"template_id": "wp-outdated"},
            description="Detected an outdated WordPress installation.",
        )

        created = correlate_asset_findings(session, uuid.UUID(asset_id))
        session.commit()

        rules = {r.rule for r in created}
        assert RULE_SHARED_TECHNOLOGY in rules
    finally:
        session.close()


async def test_correlate_is_idempotent_no_duplicate_relations_on_rerun():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        nmap_f = _make_finding(
            session, asset_id, "nmap", "Open port 80/tcp (http)", "10.0.0.1",
            {"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
        )
        whatweb_f = _make_finding(
            session, asset_id, "whatweb", "Apache detected", "http://10.0.0.1/",
            {"plugin": "Apache"},
        )

        first_pass = correlate_asset_findings(session, uuid.UUID(asset_id))
        session.commit()
        second_pass = correlate_asset_findings(session, uuid.UUID(asset_id))
        session.commit()

        assert len(first_pass) == 1
        assert second_pass == []  # nothing new -- already exists

        # Scoped to this test's own two findings -- the shared, non-isolated
        # test DB (see docs/development.md) accumulates relations from every
        # other test in the same run, so an unfiltered count would be flaky.
        total = session.execute(
            select(FindingRelation).where(
                FindingRelation.finding_id.in_([nmap_f.id, whatweb_f.id]),
                FindingRelation.related_finding_id.in_([nmap_f.id, whatweb_f.id]),
            )
        ).scalars().all()
        assert len(total) == 1
    finally:
        session.close()


async def test_correlate_fewer_than_two_findings_is_noop():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        _make_finding(
            session, asset_id, "nmap", "Open port 80/tcp (http)", "10.0.0.1",
            {"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
        )
        created = correlate_asset_findings(session, uuid.UUID(asset_id))
        assert created == []
    finally:
        session.close()


def test_correlate_none_asset_id_is_noop():
    session = get_sync_session()
    try:
        assert correlate_asset_findings(session, None) == []
    finally:
        session.close()
