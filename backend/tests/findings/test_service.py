import uuid
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.findings.service import _merge_observation, upsert_finding
from app.main import app
from app.models.finding import Finding, FindingStatus
from app.models.job import Job, JobStatus


async def _make_asset() -> str:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Findings Service Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()
    return asset["id"]


def _make_job(session, asset_id: str | None, finished_at: datetime | None = None) -> Job:
    job = Job(
        id=uuid.uuid4(),
        tool="nmap",
        target="10.0.0.1",
        target_id=uuid.UUID(asset_id) if asset_id else None,
        params={},
        status=JobStatus.SUCCESS,
        finished_at=finished_at or datetime.now(timezone.utc),
    )
    session.add(job)
    session.commit()
    return job


def _finding_data(**overrides) -> dict:
    data = {
        "target": "10.0.0.1",
        "source_tool": "nmap",
        "title": "Open port 80/tcp (http)",
        "description": "nmap found port 80/tcp open.",
        "severity": "INFO",
        "evidence": {"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
        "cve_ids": [],
    }
    data.update(overrides)
    return data


async def test_upsert_finding_creates_new_finding_on_first_observation():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        job = _make_job(session, asset_id)
        finding = upsert_finding(session, job, _finding_data())
        session.commit()

        assert finding.observation_count == 1
        assert finding.source_tools == ["nmap"]
        assert finding.observation_job_ids == [str(job.id)]
        assert finding.signature is not None
        assert finding.status == FindingStatus.NEW
        assert finding.first_seen == finding.last_seen
    finally:
        session.close()


async def test_upsert_finding_second_identical_observation_merges_not_duplicates():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        job1 = _make_job(session, asset_id)
        first = upsert_finding(session, job1, _finding_data())
        session.commit()
        first_id = first.id

        job2 = _make_job(session, asset_id)
        second = upsert_finding(session, job2, _finding_data())
        session.commit()

        assert second.id == first_id
        assert second.observation_count == 2
        assert second.observation_job_ids == [str(job1.id), str(job2.id)]
        assert second.source_tools == ["nmap"]  # same tool, not duplicated

        total = session.query(Finding).filter(Finding.signature == first.signature).count()
        assert total == 1
    finally:
        session.close()


async def test_upsert_finding_cross_tool_same_cve_merges_into_one_finding():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        job_nuclei = _make_job(session, asset_id)
        job_nuclei.tool = "nuclei"
        session.commit()
        nuclei_data = _finding_data(
            source_tool="nuclei",
            title="CVE-2024-9999 detected",
            evidence={"template_id": "t", "cve_ids": ["CVE-2024-9999"]},
            cve_ids=["CVE-2024-9999"],
        )
        first = upsert_finding(session, job_nuclei, nuclei_data)
        session.commit()

        job_other = _make_job(session, asset_id)
        job_other.tool = "nmap"
        session.commit()
        other_data = _finding_data(
            source_tool="othertool",
            title="A completely different observed title",
            evidence={"cve_ids": ["CVE-2024-9999"]},
            cve_ids=["CVE-2024-9999"],
        )
        second = upsert_finding(session, job_other, other_data)
        session.commit()

        assert second.id == first.id
        assert set(second.source_tools) == {"nuclei", "othertool"}
        assert second.observation_count == 2
    finally:
        session.close()


async def test_upsert_finding_never_overwrites_known_recommendation_with_null():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        job1 = _make_job(session, asset_id)
        first = upsert_finding(session, job1, _finding_data(recommendation="Patch nginx to 1.25+"))
        session.commit()
        assert first.recommendation == "Patch nginx to 1.25+"

        job2 = _make_job(session, asset_id)
        second = upsert_finding(session, job2, _finding_data(recommendation=None))
        session.commit()

        assert second.recommendation == "Patch nginx to 1.25+"  # not clobbered by null
    finally:
        session.close()


async def test_upsert_finding_latest_evidence_wins():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        job1 = _make_job(session, asset_id)
        upsert_finding(session, job1, _finding_data(evidence={"port": 80, "protocol": "tcp", "state": "open", "service": "http", "version": "1.0"}))
        session.commit()

        job2 = _make_job(session, asset_id)
        second = upsert_finding(session, job2, _finding_data(evidence={"port": 80, "protocol": "tcp", "state": "open", "service": "http", "version": "2.0"}))
        session.commit()

        assert second.evidence["version"] == "2.0"
    finally:
        session.close()


async def test_upsert_finding_first_seen_never_regresses_last_seen_always_advances():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        base = datetime.now(timezone.utc)
        job1 = _make_job(session, asset_id, finished_at=base)
        first = upsert_finding(session, job1, _finding_data())
        session.commit()

        # A later job (e.g. a delayed worker retry) reports an earlier
        # observed_at than what's already recorded -- first_seen must not
        # move forward, and a genuinely later one must push last_seen ahead.
        job_earlier = _make_job(session, asset_id, finished_at=base - timedelta(hours=1))
        upsert_finding(session, job_earlier, _finding_data())
        session.commit()

        job_later = _make_job(session, asset_id, finished_at=base + timedelta(hours=1))
        merged = upsert_finding(session, job_later, _finding_data())
        session.commit()

        assert merged.first_seen == base - timedelta(hours=1)
        assert merged.last_seen == base + timedelta(hours=1)
        assert merged.id == first.id
    finally:
        session.close()


async def test_upsert_finding_without_asset_never_dedups():
    session = get_sync_session()
    try:
        job1 = _make_job(session, None)
        job2 = _make_job(session, None)
        first = upsert_finding(session, job1, _finding_data())
        second = upsert_finding(session, job2, _finding_data())
        session.commit()

        assert first.signature is None
        assert second.signature is None
        assert first.id != second.id  # no Asset -> no identity -> never merged
    finally:
        session.close()


async def test_upsert_finding_reobserving_false_positive_reopens_it():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        job1 = _make_job(session, asset_id)
        first = upsert_finding(session, job1, _finding_data())
        session.commit()

        first.status = FindingStatus.FALSE_POSITIVE
        session.commit()

        job2 = _make_job(session, asset_id)
        second = upsert_finding(session, job2, _finding_data())
        session.commit()

        assert second.id == first.id
        assert second.status == FindingStatus.REOPENED
    finally:
        session.close()


async def test_upsert_finding_reobserving_accepted_risk_never_reopens():
    asset_id = await _make_asset()
    session = get_sync_session()
    try:
        job1 = _make_job(session, asset_id)
        first = upsert_finding(session, job1, _finding_data())
        session.commit()

        first.status = FindingStatus.ACCEPTED_RISK
        session.commit()

        job2 = _make_job(session, asset_id)
        second = upsert_finding(session, job2, _finding_data())
        session.commit()

        assert second.id == first.id
        assert second.status == FindingStatus.ACCEPTED_RISK
    finally:
        session.close()


def test_merge_observation_unions_cve_ids_without_losing_existing_ones():
    # Exercises the merge invariant directly: a known CVE must survive even
    # if a later observation's payload doesn't repeat it (defensive -- in
    # practice a matching CVE-tier signature already implies an identical
    # CVE set, see app/findings/signature.py, but the merge itself must
    # never regress if that ever changes).
    # A CVE id unique to this test run -- tests/intel/test_sync.py::sync_nvd_cvss
    # sweeps *every* Finding in this shared, non-isolated test DB (see
    # docs/development.md) that's missing a CVSS score, so a low-entropy id
    # like "CVE-2024-0001" risks colliding with another test's own row
    # (same convention as tests/risk/test_service.py's unique_cve helper).
    unique_cve = f"CVE-9999-{uuid.uuid4().hex[:8]}"

    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool="nuclei", target="x", params={}, status=JobStatus.SUCCESS)
        session.add(job)
        session.commit()

        finding = Finding(
            job_id=job.id,
            target="x",
            source_tool="nuclei",
            title="t",
            description="",
            severity="INFO",
            evidence={},
            cve_ids=[unique_cve],
            source_tools=["nuclei"],
            observation_job_ids=[str(job.id)],
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        session.add(finding)
        session.commit()

        _merge_observation(
            session,
            finding,
            job,
            _finding_data(source_tool="nuclei", cve_ids=[]),
            cve_ids=[],
            observed_at=datetime.now(timezone.utc),
        )
        session.commit()

        assert unique_cve in finding.cve_ids
    finally:
        session.close()
