import uuid
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.main import app
from app.models.asset import Asset
from app.models.finding import Confidence, Finding, Severity
from app.models.job import Job, JobStatus
from app.models.vulnerability_intel import CisaKevEntry, IntelSyncState, VulnerabilityIntel
from app.risk.service import (
    build_risk_inputs,
    recalculate_finding_risk,
    recalculate_findings_for_asset,
    recalculate_findings_for_cve,
    seed_cvss_from_tool,
)


async def _make_asset(criticality="MEDIUM", hostname="cyberlab-kali") -> tuple[str, str]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Risk Service Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "a", "hostname": hostname, "type": "CONTAINER", "criticality": criticality},
            )
        ).json()
    return project["id"], asset["id"]


def _mark_kev_synced(session) -> None:
    """IntelSyncState.source is a primary key -- get-or-create, since
    multiple tests in this shared (non-isolated) test DB each need
    "cisa_kev" marked as successfully synced at least once."""
    state = session.get(IntelSyncState, "cisa_kev")
    if state is None:
        state = IntelSyncState(source="cisa_kev")
        session.add(state)
    state.last_success_at = datetime.now(timezone.utc)
    session.commit()


def _make_finding(asset_id: str, cve_ids: list[str] | None = None, confidence=Confidence.MEDIUM) -> Finding:
    session = get_sync_session()
    try:
        job = Job(
            id=uuid.uuid4(),
            tool="nuclei",
            target="x",
            target_id=uuid.UUID(asset_id),
            params={},
            status=JobStatus.SUCCESS,
        )
        session.add(job)
        session.commit()

        finding = Finding(
            job_id=job.id,
            target="x",
            source_tool="nuclei",
            title="t",
            description="",
            severity=Severity.MEDIUM,
            confidence=confidence,
            evidence={},
            cve_ids=cve_ids or [],
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)
        return finding
    finally:
        session.close()


async def test_build_risk_inputs_no_cve_leaves_cvss_epss_kev_none():
    _, asset_id = await _make_asset()
    finding = _make_finding(asset_id)
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        inputs = build_risk_inputs(session, finding)
    finally:
        session.close()
    assert inputs.cvss_score is None
    assert inputs.epss_score is None
    assert inputs.kev is None
    assert inputs.asset_criticality is not None


async def test_build_risk_inputs_unknown_cve_no_intel_row_stays_unscored():
    _, asset_id = await _make_asset()
    # A CVE id unique to this test run -- other tests/modules sharing this
    # DB (no per-test isolation, same convention as tests/scheduling/) sync
    # real intelligence data keyed only by CVE string, so reusing a
    # low-entropy id like "CVE-0000-00001" risks a collision.
    unique_cve = f"CVE-9999-{uuid.uuid4().hex[:8]}"
    finding = _make_finding(asset_id, cve_ids=[unique_cve])
    session = get_sync_session()
    try:
        # IntelSyncState("cisa_kev") is a single global row: other tests in
        # this shared DB legitimately mark it synced to exercise the
        # KEV=true/false paths, so "never synced" can't be assumed to still
        # hold here -- force the precondition this test actually wants.
        existing_state = session.get(IntelSyncState, "cisa_kev")
        if existing_state is not None:
            session.delete(existing_state)
            session.commit()

        finding = session.get(Finding, finding.id)
        inputs = build_risk_inputs(session, finding)
    finally:
        session.close()
    assert inputs.cvss_score is None
    assert inputs.kev is None  # no CISA KEV sync has run at all


async def test_build_risk_inputs_picks_worst_cvss_among_multiple_cves():
    _, asset_id = await _make_asset()
    session = get_sync_session()
    try:
        session.add(VulnerabilityIntel(cve="CVE-2020-0001", cvss_score=4.0))
        session.add(VulnerabilityIntel(cve="CVE-2020-0002", cvss_score=9.1))
        session.commit()
    finally:
        session.close()

    finding = _make_finding(asset_id, cve_ids=["CVE-2020-0001", "CVE-2020-0002"])
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        inputs = build_risk_inputs(session, finding)
    finally:
        session.close()
    assert inputs.cvss_score == 9.1


async def test_build_risk_inputs_kev_true_once_synced():
    _, asset_id = await _make_asset()
    session = get_sync_session()
    try:
        _mark_kev_synced(session)
        if session.get(CisaKevEntry, "CVE-2021-44228") is None:
            session.add(CisaKevEntry(cve_id="CVE-2021-44228", known_ransomware_campaign_use=True))
            session.commit()
    finally:
        session.close()

    finding = _make_finding(asset_id, cve_ids=["CVE-2021-44228"])
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        inputs = build_risk_inputs(session, finding)
    finally:
        session.close()
    assert inputs.kev is True


async def test_build_risk_inputs_kev_false_when_synced_but_absent():
    _, asset_id = await _make_asset()
    session = get_sync_session()
    try:
        _mark_kev_synced(session)
    finally:
        session.close()

    finding = _make_finding(asset_id, cve_ids=["CVE-2021-999999"])
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        inputs = build_risk_inputs(session, finding)
    finally:
        session.close()
    assert inputs.kev is False


async def test_recalculate_finding_risk_writes_cache_columns():
    _, asset_id = await _make_asset(criticality="CRITICAL")
    session = get_sync_session()
    try:
        session.add(VulnerabilityIntel(cve="CVE-2022-0001", cvss_score=9.0, epss_score=0.8))
        session.commit()
    finally:
        session.close()

    finding = _make_finding(asset_id, cve_ids=["CVE-2022-0001"])
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        result = recalculate_finding_risk(session, finding)
        session.commit()
        assert finding.risk_score == result.score
        assert finding.risk_priority == result.priority
        assert finding.cvss_score == 9.0
        assert finding.epss_score == 0.8
        assert finding.risk_calculated_at is not None
    finally:
        session.close()


async def test_recalculate_findings_for_cve_only_touches_matching_findings():
    _, asset_id = await _make_asset()
    match = _make_finding(asset_id, cve_ids=["CVE-2023-1111"])
    other = _make_finding(asset_id, cve_ids=["CVE-2023-2222"])

    session = get_sync_session()
    try:
        updated = recalculate_findings_for_cve(session, "CVE-2023-1111")
        session.commit()
        updated_ids = {f.id for f in updated}
        assert match.id in updated_ids
        assert other.id not in updated_ids
    finally:
        session.close()


async def test_recalculate_findings_for_asset_recomputes_after_criticality_change():
    project_id, asset_id = await _make_asset(criticality="LOW")
    session = get_sync_session()
    try:
        session.add(VulnerabilityIntel(cve="CVE-2024-0001", cvss_score=8.0))
        session.commit()
    finally:
        session.close()

    finding = _make_finding(asset_id, cve_ids=["CVE-2024-0001"])
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        recalculate_finding_risk(session, finding)
        session.commit()
        score_at_low = finding.risk_score
    finally:
        session.close()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.patch(f"/api/assets/{asset_id}", json={"criticality": "CRITICAL"})
        assert response.status_code == 200

    session = get_sync_session()
    try:
        refreshed = session.get(Finding, finding.id)
        assert refreshed.risk_score is not None
        assert refreshed.risk_score > score_at_low
    finally:
        session.close()


async def test_seed_cvss_from_tool_never_overwrites_existing_value():
    session = get_sync_session()
    try:
        session.add(VulnerabilityIntel(cve="CVE-2025-0001", cvss_score=5.0, cvss_source="nvd"))
        session.commit()

        updated = seed_cvss_from_tool(
            session,
            [{"cve": "CVE-2025-0001", "cvss_score": 9.9, "cvss_version": "3.1", "cvss_vector": "CVSS:3.1/x"}],
        )
        session.commit()
        assert updated == set()

        intel = session.get(VulnerabilityIntel, "CVE-2025-0001")
        assert intel.cvss_score == 5.0  # untouched
        assert intel.cvss_source == "nvd"
    finally:
        session.close()


async def test_seed_cvss_from_tool_creates_new_row():
    session = get_sync_session()
    try:
        updated = seed_cvss_from_tool(
            session,
            [{"cve": "CVE-2025-0002", "cvss_score": 7.3, "cvss_version": "3.1", "cvss_vector": "CVSS:3.1/y"}],
        )
        session.commit()
        assert updated == {"CVE-2025-0002"}

        intel = session.get(VulnerabilityIntel, "CVE-2025-0002")
        assert intel.cvss_score == 7.3
        assert intel.cvss_source == "nuclei_template"
    finally:
        session.close()
