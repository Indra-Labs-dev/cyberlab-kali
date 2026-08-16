import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.findings.correlation import correlate_asset_findings
from app.main import app
from app.models.finding import Finding, FindingStatus
from app.models.job import Job, JobStatus


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_asset(client) -> str:
    project = (await client.post("/api/projects", json={"name": "Findings API Fixture"})).json()
    asset = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
        )
    ).json()
    return asset["id"]


def _make_finding(
    asset_id: str,
    source_tool: str = "nmap",
    title: str = "t",
    evidence: dict | None = None,
    status: FindingStatus = FindingStatus.NEW,
    target: str = "10.0.0.1",
) -> str:
    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool=source_tool, target=target, target_id=uuid.UUID(asset_id), params={}, status=JobStatus.SUCCESS)
        session.add(job)
        session.commit()

        finding = Finding(
            job_id=job.id,
            target=target,
            source_tool=source_tool,
            title=title,
            description="",
            severity="INFO",
            evidence=evidence or {},
            status=status,
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)
        return str(finding.id)
    finally:
        session.close()


async def test_list_findings_filters_by_status(client):
    asset_id = await _make_asset(client)
    new_id = _make_finding(asset_id, status=FindingStatus.NEW)
    confirmed_id = _make_finding(asset_id, status=FindingStatus.CONFIRMED)

    response = await client.get("/api/findings", params={"status": "CONFIRMED", "target_id": asset_id})
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()}
    assert confirmed_id in ids
    assert new_id not in ids


async def test_list_findings_active_only_includes_unresolved_statuses(client):
    asset_id = await _make_asset(client)
    new_id = _make_finding(asset_id, status=FindingStatus.NEW)
    confirmed_id = _make_finding(asset_id, status=FindingStatus.CONFIRMED)
    in_review_id = _make_finding(asset_id, status=FindingStatus.IN_REVIEW)
    reopened_id = _make_finding(asset_id, status=FindingStatus.REOPENED)

    response = await client.get("/api/findings", params={"active_only": "true", "target_id": asset_id})
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()}
    assert {new_id, confirmed_id, in_review_id, reopened_id} <= ids


async def test_list_findings_active_only_excludes_resolved_statuses(client):
    asset_id = await _make_asset(client)
    accepted_id = _make_finding(asset_id, status=FindingStatus.ACCEPTED_RISK)
    false_positive_id = _make_finding(asset_id, status=FindingStatus.FALSE_POSITIVE)
    remediated_id = _make_finding(asset_id, status=FindingStatus.REMEDIATED)

    response = await client.get("/api/findings", params={"active_only": "true", "target_id": asset_id})
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()}
    assert ids.isdisjoint({accepted_id, false_positive_id, remediated_id})


async def test_list_findings_explicit_status_overrides_active_only(client):
    """An explicit `status` always wins -- active_only is only a shortcut
    for when nothing more specific was asked for, never a second, silently
    conflicting filter."""
    asset_id = await _make_asset(client)
    accepted_id = _make_finding(asset_id, status=FindingStatus.ACCEPTED_RISK)
    new_id = _make_finding(asset_id, status=FindingStatus.NEW)

    response = await client.get(
        "/api/findings", params={"active_only": "true", "status": "ACCEPTED_RISK", "target_id": asset_id}
    )
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()}
    assert accepted_id in ids  # explicit status wins even though it's not "active"
    assert new_id not in ids


async def test_list_findings_active_only_defaults_to_false_no_behavior_change(client):
    asset_id = await _make_asset(client)
    accepted_id = _make_finding(asset_id, status=FindingStatus.ACCEPTED_RISK)
    new_id = _make_finding(asset_id, status=FindingStatus.NEW)

    response = await client.get("/api/findings", params={"target_id": asset_id})
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()}
    assert {accepted_id, new_id} <= ids  # unfiltered by default, exactly as before this change


async def test_list_findings_filters_by_source_tool(client):
    asset_id = await _make_asset(client)
    nmap_id = _make_finding(asset_id, source_tool="nmap")
    whatweb_id = _make_finding(asset_id, source_tool="whatweb")

    response = await client.get("/api/findings", params={"source_tool": "whatweb", "target_id": asset_id})
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()}
    assert whatweb_id in ids
    assert nmap_id not in ids


async def test_get_finding_history_returns_404_for_unknown_finding(client):
    response = await client.get(f"/api/findings/{uuid.uuid4()}/history")
    assert response.status_code == 404


async def test_get_finding_relations_returns_404_for_unknown_finding(client):
    response = await client.get(f"/api/findings/{uuid.uuid4()}/relations")
    assert response.status_code == 404


async def test_patch_status_returns_404_for_unknown_finding(client):
    response = await client.patch(f"/api/findings/{uuid.uuid4()}/status", json={"status": "CONFIRMED"})
    assert response.status_code == 404


async def test_patch_status_valid_transition_records_history(client):
    asset_id = await _make_asset(client)
    finding_id = _make_finding(asset_id, status=FindingStatus.NEW)

    response = await client.patch(f"/api/findings/{finding_id}/status", json={"status": "CONFIRMED", "reason": "verified manually"})
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"

    history_response = await client.get(f"/api/findings/{finding_id}/history")
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["old_status"] == "NEW"
    assert history[0]["new_status"] == "CONFIRMED"
    assert history[0]["reason"] == "verified manually"
    assert history[0]["triggered_by"] == "manual"


async def test_patch_status_invalid_transition_rejected_and_unchanged(client):
    asset_id = await _make_asset(client)
    finding_id = _make_finding(asset_id, status=FindingStatus.NEW)

    response = await client.patch(f"/api/findings/{finding_id}/status", json={"status": "REMEDIATED"})
    assert response.status_code == 400

    get_response = await client.get(f"/api/findings/{finding_id}")
    assert get_response.json()["status"] == "NEW"

    history_response = await client.get(f"/api/findings/{finding_id}/history")
    assert history_response.json() == []


async def test_patch_status_accepted_risk_cannot_be_bypassed_to_arbitrary_status(client):
    asset_id = await _make_asset(client)
    finding_id = _make_finding(asset_id, status=FindingStatus.ACCEPTED_RISK)

    # Only REOPENED is valid from ACCEPTED_RISK -- confirm CONFIRMED/IN_REVIEW/etc are rejected.
    response = await client.patch(f"/api/findings/{finding_id}/status", json={"status": "IN_REVIEW"})
    assert response.status_code == 400


async def test_get_finding_relations_normalized_from_both_perspectives(client):
    asset_id = await _make_asset(client)
    nmap_id = _make_finding(
        asset_id, source_tool="nmap", title="Open port 80/tcp (http)",
        evidence={"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
    )
    whatweb_id = _make_finding(
        asset_id, source_tool="whatweb", title="Apache detected", evidence={"plugin": "Apache"},
        target="http://10.0.0.1/",
    )

    session = get_sync_session()
    try:
        correlate_asset_findings(session, uuid.UUID(asset_id))
        session.commit()
    finally:
        session.close()

    for requested_id, other_id in [(nmap_id, whatweb_id), (whatweb_id, nmap_id)]:
        response = await client.get(f"/api/findings/{requested_id}/relations")
        assert response.status_code == 200
        relations = response.json()
        assert len(relations) == 1
        assert relations[0]["finding_id"] == requested_id
        assert relations[0]["related_finding_id"] == other_id
        assert relations[0]["rule"] == "RULE_NMAP_WHATWEB_PORT"
