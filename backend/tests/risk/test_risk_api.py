import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.main import app
from app.models.finding import Finding, Severity
from app.models.job import Job, JobStatus
from app.models.vulnerability_intel import CisaKevEntry, IntelSyncState, VulnerabilityIntel


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_asset(client, criticality="MEDIUM") -> tuple[str, str]:
    project = (await client.post("/api/projects", json={"name": "Risk API Fixture"})).json()
    asset = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER", "criticality": criticality},
        )
    ).json()
    return project["id"], asset["id"]


def _seed_vulnerability_intel(session, cve: str, **fields) -> None:
    """Phase 23 -- VulnerabilityIntel.cve is a primary key: get-or-create so
    this fixture is safe to run repeatedly against this shared,
    non-recreated test DB. Previously a plain `session.add(...)`, which
    raised an unhandled IntegrityError on any second run (see
    tests/risk/test_service.py's identical helper for the same reasoning)."""
    existing = session.get(VulnerabilityIntel, cve)
    if existing is None:
        session.add(VulnerabilityIntel(cve=cve, **fields))
    else:
        for key, value in fields.items():
            setattr(existing, key, value)


def _make_scored_finding(asset_id: str, cve_ids: list[str] | None = None, severity: Severity = Severity.HIGH) -> str:
    from app.risk.service import recalculate_finding_risk

    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool="nuclei", target="x", target_id=uuid.UUID(asset_id), params={}, status=JobStatus.SUCCESS)
        session.add(job)
        session.commit()

        finding = Finding(
            job_id=job.id,
            target="x",
            source_tool="nuclei",
            title="t",
            description="",
            severity=severity,
            evidence={},
            cve_ids=cve_ids or [],
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)
        recalculate_finding_risk(session, finding)
        session.commit()
        return str(finding.id)
    finally:
        session.close()


async def test_get_finding_risk_detail(client):
    _, asset_id = await _make_asset(client)
    session = get_sync_session()
    try:
        _seed_vulnerability_intel(session, "CVE-2030-11111", cvss_score=8.5, cvss_version="3.1", epss_score=0.4, epss_percentile=0.7)
        session.commit()
    finally:
        session.close()

    finding_id = _make_scored_finding(asset_id, cve_ids=["CVE-2030-11111"])
    response = await client.get(f"/api/findings/{finding_id}/risk")
    assert response.status_code == 200
    body = response.json()
    assert body["inputs"]["cvss_score"] == 8.5
    assert body["inputs"]["cvss_version"] == "3.1"
    assert body["inputs"]["epss_score"] == 0.4
    assert 0 <= body["score"] <= 100
    assert len(body["explanation"]) == 5
    assert len(body["components"]) == 3


async def test_get_finding_risk_404_for_nonexistent(client):
    response = await client.get("/api/findings/00000000-0000-0000-0000-000000000000/risk")
    assert response.status_code == 404


async def test_finding_without_cve_still_gets_a_risk_score(client):
    _, asset_id = await _make_asset(client)
    finding_id = _make_scored_finding(asset_id, cve_ids=[])
    response = await client.get(f"/api/findings/{finding_id}/risk")
    assert response.status_code == 200
    body = response.json()
    assert body["inputs"]["cvss_score"] is None
    assert body["inputs"]["kev"] is None
    assert body["score"] is not None  # severity fallback still produces a score


async def test_finding_with_unknown_cve_no_intelligence_data(client):
    # Phase 23 -- this test's premise is "this CVE has no intelligence data
    # at all". Unlike the hardcoded-insert-collision fragility fixed
    # elsewhere in this file, the risk here is a *different* test's
    # unscoped sync_nvd_cvss() call (which processes every currently-
    # unscored CVE across the whole shared test DB, not just its own
    # fixture's) later giving this CVE a real score -- explicitly clear any
    # leftover row before asserting freshness, rather than assuming it.
    session = get_sync_session()
    try:
        existing = session.get(VulnerabilityIntel, "CVE-1999-00001")
        if existing is not None:
            session.delete(existing)
            session.commit()
    finally:
        session.close()

    _, asset_id = await _make_asset(client)
    finding_id = _make_scored_finding(asset_id, cve_ids=["CVE-1999-00001"])
    response = await client.get(f"/api/findings/{finding_id}/risk")
    assert response.status_code == 200
    body = response.json()
    assert body["inputs"]["cvss_score"] is None
    assert any("No CVSS available" in line for line in body["explanation"])


async def test_asset_risk_summary_counts_by_priority(client):
    _, asset_id = await _make_asset(client, criticality="CRITICAL")
    session = get_sync_session()
    try:
        _seed_vulnerability_intel(session, "CVE-2030-22222", cvss_score=9.8, epss_score=0.9)
        session.commit()
    finally:
        session.close()

    _make_scored_finding(asset_id, cve_ids=["CVE-2030-22222"])
    _make_scored_finding(asset_id, cve_ids=[])

    response = await client.get(f"/api/assets/{asset_id}/risk-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_findings"] == 2
    assert body["highest_risk_score"] is not None
    assert body["critical_findings"] + body["high_findings"] + body["medium_findings"] + body["low_findings"] + body["informational_findings"] == 2


async def test_asset_risk_summary_404_for_nonexistent(client):
    response = await client.get("/api/assets/00000000-0000-0000-0000-000000000000/risk-summary")
    assert response.status_code == 404


async def test_asset_risk_summary_empty_asset(client):
    _, asset_id = await _make_asset(client)
    response = await client.get(f"/api/assets/{asset_id}/risk-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_findings"] == 0
    assert body["highest_risk_score"] is None


async def test_list_findings_filter_by_kev(client):
    _, asset_id = await _make_asset(client)
    session = get_sync_session()
    try:
        _seed_vulnerability_intel(session, "CVE-2030-33333", cvss_score=9.0)
        _existing = session.get(IntelSyncState, "cisa_kev")
        from datetime import datetime, timezone

        if _existing is None:
            _existing = IntelSyncState(source="cisa_kev")
            session.add(_existing)
        _existing.last_success_at = datetime.now(timezone.utc)
        if session.get(CisaKevEntry, "CVE-2030-33333") is None:
            session.add(CisaKevEntry(cve_id="CVE-2030-33333", known_ransomware_campaign_use=False))
        session.commit()
    finally:
        session.close()

    kev_finding_id = _make_scored_finding(asset_id, cve_ids=["CVE-2030-33333"])
    _make_scored_finding(asset_id, cve_ids=[])

    response = await client.get("/api/findings?kev=true&limit=500")
    assert response.status_code == 200
    ids = [f["id"] for f in response.json()]
    assert kev_finding_id in ids
    assert all(f["kev"] is True for f in response.json())


async def test_list_findings_sort_by_risk_score_desc(client):
    # Deliberately separate assets/severities (rather than sharing one) so
    # the ranking is unambiguous regardless of KEV sync state possibly
    # having changed globally from another test sharing this DB -- even a
    # confirmed KEV=false for the high finding's CVE must not close the gap.
    _, high_asset_id = await _make_asset(client, criticality="CRITICAL")
    _, low_asset_id = await _make_asset(client, criticality="LOW")
    session = get_sync_session()
    try:
        _seed_vulnerability_intel(session, "CVE-2030-44444", cvss_score=9.9, epss_score=0.95)
        session.commit()
    finally:
        session.close()

    high_id = _make_scored_finding(high_asset_id, cve_ids=["CVE-2030-44444"])
    low_id = _make_scored_finding(low_asset_id, cve_ids=[], severity=Severity.INFO)

    response = await client.get("/api/findings?sort=risk_score_desc&limit=500")
    assert response.status_code == 200
    ids = [f["id"] for f in response.json()]
    assert ids.index(high_id) < ids.index(low_id)


async def test_list_findings_filter_by_min_risk_score(client):
    _, asset_id = await _make_asset(client, criticality="CRITICAL")
    session = get_sync_session()
    try:
        _seed_vulnerability_intel(session, "CVE-2030-55555", cvss_score=9.9, epss_score=0.95)
        session.commit()
    finally:
        session.close()

    high_id = _make_scored_finding(asset_id, cve_ids=["CVE-2030-55555"])
    response = await client.get("/api/findings?min_risk_score=80&limit=500")
    assert response.status_code == 200
    ids = [f["id"] for f in response.json()]
    assert high_id in ids
    assert all(f["risk_score"] is not None and f["risk_score"] >= 80 for f in response.json())


async def test_list_findings_filter_by_priority(client):
    _, asset_id = await _make_asset(client)
    finding_id = _make_scored_finding(asset_id, cve_ids=[], severity=Severity.INFO)
    response = await client.get("/api/findings?priority=INFORMATIONAL&limit=500")
    assert response.status_code == 200
    ids = [f["id"] for f in response.json()]
    assert finding_id in ids
    assert all(f["risk_priority"] == "INFORMATIONAL" for f in response.json())


async def test_intelligence_status_lists_sources(client):
    response = await client.get("/api/intelligence/status")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_intelligence_sync_trigger_enqueues(client, monkeypatch):
    from unittest.mock import MagicMock

    mock_queue = MagicMock()
    monkeypatch.setattr("app.api.routes.intelligence.get_queue", lambda: mock_queue)

    response = await client.post("/api/intelligence/sync")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    mock_queue.enqueue.assert_called_once()
