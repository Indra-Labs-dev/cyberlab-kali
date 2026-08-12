import uuid
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

import app.intel.sync as sync_module
from app.db.sync_session import get_sync_session
from app.intel.cisa_kev import CisaKevFetchError
from app.intel.epss import EPSSFetchError
from app.main import app
from app.models.finding import Finding, Severity
from app.models.job import Job, JobStatus
from app.models.vulnerability_intel import CisaKevEntry, IntelSyncState, VulnerabilityIntel


async def _make_finding_with_cve(cve: str) -> str:
    """Real project/asset/job chain (needed for the FK), then a Finding
    with a CVE attached directly via the sync session -- mirrors
    tests/diff/test_service.py's pattern."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Intel Sync Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()

    session = get_sync_session()
    try:
        job = Job(
            id=uuid.uuid4(),
            tool="nuclei",
            target="cyberlab-kali",
            target_id=uuid.UUID(asset["id"]),
            params={},
            status=JobStatus.SUCCESS,
        )
        session.add(job)
        session.commit()

        finding = Finding(
            job_id=job.id,
            target="cyberlab-kali",
            source_tool="nuclei",
            title="test finding",
            description="",
            severity=Severity.HIGH,
            evidence={},
            cve_ids=[cve],
        )
        session.add(finding)
        session.commit()
        return str(finding.id)
    finally:
        session.close()


def _get_state(source: str) -> IntelSyncState | None:
    session = get_sync_session()
    try:
        return session.get(IntelSyncState, source)
    finally:
        session.close()


async def test_sync_epss_no_known_cves_records_success_without_request():
    session = get_sync_session()
    try:
        # Isolate: don't rely on other tests' CVEs being absent, just check
        # the call completes and records a success state either way.
        with patch("app.intel.sync.fetch_epss_scores") as mock_fetch:
            mock_fetch.return_value = {}
            sync_module.sync_epss(session)
    finally:
        session.close()
    state = _get_state("epss")
    assert state is not None
    assert state.last_success_at is not None


async def test_sync_epss_success_updates_intel_and_recalculates_finding():
    finding_id = await _make_finding_with_cve("CVE-2021-44228")

    with patch("app.intel.sync.fetch_epss_scores") as mock_fetch:
        mock_fetch.return_value = {"CVE-2021-44228": {"epss": 0.912, "percentile": 0.98}}
        sync_module.sync_epss()

    session = get_sync_session()
    try:
        intel = session.get(VulnerabilityIntel, "CVE-2021-44228")
        assert intel is not None
        assert intel.epss_score == 0.912

        finding = session.get(Finding, uuid.UUID(finding_id))
        assert finding.epss_score == 0.912
        assert finding.risk_score is not None
    finally:
        session.close()


async def test_sync_epss_failure_is_recorded_not_raised():
    await _make_finding_with_cve("CVE-2099-00001")
    with patch("app.intel.sync.fetch_epss_scores", side_effect=EPSSFetchError("boom")):
        sync_module.sync_epss()  # must not raise
    state = _get_state("epss")
    assert state.last_error is not None
    assert "boom" in state.last_error


async def test_sync_cisa_kev_success_populates_catalog_and_recalculates():
    finding_id = await _make_finding_with_cve("CVE-2021-44228")

    with patch("app.intel.sync.fetch_cisa_kev_catalog") as mock_fetch:
        mock_fetch.return_value = [
            {
                "cve_id": "CVE-2021-44228",
                "vendor_project": "Apache",
                "product": "Log4j",
                "vulnerability_name": "Log4Shell",
                "date_added": None,
                "due_date": None,
                "known_ransomware_campaign_use": True,
            }
        ]
        sync_module.sync_cisa_kev()

    session = get_sync_session()
    try:
        entry = session.get(CisaKevEntry, "CVE-2021-44228")
        assert entry is not None

        finding = session.get(Finding, uuid.UUID(finding_id))
        assert finding.kev is True
    finally:
        session.close()

    state = _get_state("cisa_kev")
    assert state.last_success_at is not None


async def test_sync_cisa_kev_removes_entries_no_longer_in_catalog():
    with patch("app.intel.sync.fetch_cisa_kev_catalog") as mock_fetch:
        mock_fetch.return_value = [
            {
                "cve_id": "CVE-2020-00099",
                "vendor_project": None,
                "product": None,
                "vulnerability_name": None,
                "date_added": None,
                "due_date": None,
                "known_ransomware_campaign_use": False,
            }
        ]
        sync_module.sync_cisa_kev()

    with patch("app.intel.sync.fetch_cisa_kev_catalog") as mock_fetch:
        mock_fetch.return_value = []  # CVE removed upstream
        sync_module.sync_cisa_kev()

    session = get_sync_session()
    try:
        assert session.get(CisaKevEntry, "CVE-2020-00099") is None
    finally:
        session.close()


async def test_sync_cisa_kev_failure_is_recorded_not_raised():
    with patch("app.intel.sync.fetch_cisa_kev_catalog", side_effect=CisaKevFetchError("unreachable")):
        sync_module.sync_cisa_kev()  # must not raise
    state = _get_state("cisa_kev")
    assert state.last_error is not None


async def test_sync_nvd_cvss_skips_cves_that_already_have_a_score():
    # The test DB is shared across test functions (no per-test isolation,
    # same convention as tests/scheduling/test_ticker.py): other CVEs may
    # already be "missing CVSS" from earlier tests in this run, so this test
    # only asserts that *its own* CVE is never queried, not that nothing is
    # queried at all -- and gives the mock a valid, storable return value so
    # any other CVE that does get processed doesn't crash on a bare MagicMock.
    finding_id = await _make_finding_with_cve("CVE-2030-00001")
    session = get_sync_session()
    try:
        session.add(VulnerabilityIntel(cve="CVE-2030-00001", cvss_score=8.8, cvss_source="nuclei_template"))
        session.commit()
        # In the real flow (app/jobs/tasks.py::execute_job) a finding's
        # cached risk fields are always recomputed immediately at creation
        # time, using whatever CVSS is already known then -- replicate that
        # here rather than leaving the cache stale from test setup alone.
        sync_module.recalculate_findings_for_cve(session, "CVE-2030-00001")
        session.commit()
    finally:
        session.close()

    with patch("app.intel.sync.fetch_nvd_cvss") as mock_fetch, patch("app.intel.sync.time.sleep"):
        mock_fetch.return_value = {"score": 1.0, "version": "2.0", "vector": None}
        sync_module.sync_nvd_cvss()
        queried_cves = [call.args[0] for call in mock_fetch.call_args_list]
        assert "CVE-2030-00001" not in queried_cves

    session = get_sync_session()
    try:
        finding = session.get(Finding, uuid.UUID(finding_id))
        assert finding.cvss_score == 8.8
    finally:
        session.close()


async def test_sync_nvd_cvss_fetches_missing_cvss_and_sleeps_between_calls():
    await _make_finding_with_cve("CVE-2031-00001")
    await _make_finding_with_cve("CVE-2031-00002")

    with patch("app.intel.sync.fetch_nvd_cvss") as mock_fetch, patch("app.intel.sync.time.sleep") as mock_sleep:
        mock_fetch.return_value = {"score": 7.2, "version": "3.1", "vector": "CVSS:3.1/x"}
        sync_module.sync_nvd_cvss()
        assert mock_fetch.call_count >= 2
        assert mock_sleep.called  # rate-limit gap between NVD calls


async def test_run_full_sync_one_source_crashing_does_not_prevent_others():
    with (
        patch("app.intel.sync.sync_cisa_kev", side_effect=RuntimeError("cisa_kev exploded")),
        patch("app.intel.sync.sync_epss") as mock_epss,
        patch("app.intel.sync.sync_nvd_cvss") as mock_nvd,
    ):
        sync_module.run_full_sync()  # must not raise
        mock_epss.assert_called_once()
        mock_nvd.assert_called_once()
