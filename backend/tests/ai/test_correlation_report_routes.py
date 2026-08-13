"""Phase 18.8/18.9/18.10 -- correlation-suggestions and reports/propose
routes. Black-box HTTP tests; Findings/Jobs are inserted directly via a
sync session (mirrors tests/graph/test_queries.py's style) since the
Correlation/Report Agents only care about already-existing rows, not how
they got there.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.provider import AIProvider
from app.api.routes.ai import get_provider
from app.db.sync_session import get_sync_session
from app.main import app
from app.models.finding import Confidence, Finding, Severity
from app.models.finding_relation import FindingRelation
from app.models.job import Job, JobStatus


class FakeProvider(AIProvider):
    def __init__(self, response: str) -> None:
        self.response = response

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        return self.response


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_provider, None)


async def _make_asset(client: AsyncClient) -> tuple[str, str]:
    project = (await client.post("/api/projects", json={"name": "Correlation Route Fixture"})).json()
    asset = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"},
        )
    ).json()
    return project["id"], asset["id"]


def _make_job_and_findings(project_id: str, asset_id: str) -> tuple[str, str]:
    session = get_sync_session()
    try:
        job = Job(
            id=uuid.uuid4(),
            tool="whatweb",
            target="cyberlab-kali",
            project_id=uuid.UUID(project_id),
            target_id=uuid.UUID(asset_id),
            params={},
            status=JobStatus.SUCCESS,
        )
        session.add(job)
        session.flush()

        f1 = Finding(
            id=uuid.uuid4(), job_id=job.id, target="cyberlab-kali", source_tool="whatweb",
            title="Outdated jQuery 1.7 detected", description="", severity=Severity.LOW,
            confidence=Confidence.MEDIUM, evidence={}, cve_ids=[],
        )
        f2 = Finding(
            id=uuid.uuid4(), job_id=job.id, target="cyberlab-kali", source_tool="nuclei",
            title="Reflected XSS on /search.php", description="", severity=Severity.HIGH,
            confidence=Confidence.MEDIUM, evidence={}, cve_ids=[],
        )
        session.add_all([f1, f2])
        session.commit()
        return str(f1.id), str(f2.id)
    finally:
        session.close()


def _make_success_job(project_id: str, tool: str = "nmap") -> str:
    session = get_sync_session()
    try:
        job = Job(
            id=uuid.uuid4(), tool=tool, target="cyberlab-kali", project_id=uuid.UUID(project_id),
            params={}, status=JobStatus.SUCCESS, created_at=datetime.now(timezone.utc),
        )
        session.add(job)
        session.commit()
        return str(job.id)
    finally:
        session.close()


# --------------------------------------------------------------------------
# Correlation suggestions
# --------------------------------------------------------------------------


async def test_generate_correlation_suggestions_persists_pending(client):
    project_id, asset_id = await _make_asset(client)
    f1_id, f2_id = _make_job_and_findings(project_id, asset_id)

    plan = f'{{"suggestions": [{{"finding_id": "{f1_id}", "related_finding_id": "{f2_id}", "rationale": "outdated jQuery could enable the XSS"}}]}}'
    app.dependency_overrides[get_provider] = lambda: FakeProvider(plan)

    response = await client.post("/api/ai/correlation-suggestions", json={"target_id": asset_id})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "PENDING"
    assert {body[0]["finding_id"], body[0]["related_finding_id"]} == {f1_id, f2_id}

    # Generating a suggestion must never itself create a real
    # FindingRelation for this pair -- that only ever happens via an
    # explicit /accept. Scoped to this pair, not a global count: the shared
    # test database (see tests/scheduling/test_ticker.py's own note on
    # this) may hold FindingRelation rows from other tests.
    session = get_sync_session()
    try:
        matching = [
            r
            for r in session.query(FindingRelation).all()
            if {str(r.finding_id), str(r.related_finding_id)} == {f1_id, f2_id}
        ]
        assert matching == []
    finally:
        session.close()


async def test_generate_correlation_suggestions_is_idempotent(client):
    project_id, asset_id = await _make_asset(client)
    f1_id, f2_id = _make_job_and_findings(project_id, asset_id)
    plan = f'{{"suggestions": [{{"finding_id": "{f1_id}", "related_finding_id": "{f2_id}", "rationale": "x"}}]}}'
    app.dependency_overrides[get_provider] = lambda: FakeProvider(plan)

    first = await client.post("/api/ai/correlation-suggestions", json={"target_id": asset_id})
    second = await client.post("/api/ai/correlation-suggestions", json={"target_id": asset_id})
    assert len(first.json()) == 1
    assert len(second.json()) == 1  # not duplicated


async def test_generate_correlation_suggestions_unknown_target_404(client):
    app.dependency_overrides[get_provider] = lambda: FakeProvider('{"suggestions": []}')
    response = await client.post("/api/ai/correlation-suggestions", json={"target_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_list_correlation_suggestions_by_target(client):
    project_id, asset_id = await _make_asset(client)
    f1_id, f2_id = _make_job_and_findings(project_id, asset_id)
    plan = f'{{"suggestions": [{{"finding_id": "{f1_id}", "related_finding_id": "{f2_id}", "rationale": "x"}}]}}'
    app.dependency_overrides[get_provider] = lambda: FakeProvider(plan)
    await client.post("/api/ai/correlation-suggestions", json={"target_id": asset_id})

    response = await client.get("/api/ai/correlation-suggestions", params={"target_id": asset_id})
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_accept_suggestion_creates_finding_relation_once(client):
    project_id, asset_id = await _make_asset(client)
    f1_id, f2_id = _make_job_and_findings(project_id, asset_id)
    plan = f'{{"suggestions": [{{"finding_id": "{f1_id}", "related_finding_id": "{f2_id}", "rationale": "link"}}]}}'
    app.dependency_overrides[get_provider] = lambda: FakeProvider(plan)
    created = (await client.post("/api/ai/correlation-suggestions", json={"target_id": asset_id})).json()
    suggestion_id = created[0]["id"]

    response = await client.post(f"/api/ai/correlation-suggestions/{suggestion_id}/accept")
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"

    # Idempotent: accepting again must not create a second FindingRelation.
    second = await client.post(f"/api/ai/correlation-suggestions/{suggestion_id}/accept")
    assert second.status_code == 200
    assert second.json()["status"] == "ACCEPTED"

    session = get_sync_session()
    try:
        relations = list(
            session.query(FindingRelation).filter(FindingRelation.rule == "RULE_AI_ACCEPTED").all()
        )
        matching = [
            r for r in relations if {str(r.finding_id), str(r.related_finding_id)} == {f1_id, f2_id}
        ]
        assert len(matching) == 1
    finally:
        session.close()


async def test_dismiss_then_accept_is_rejected(client):
    project_id, asset_id = await _make_asset(client)
    f1_id, f2_id = _make_job_and_findings(project_id, asset_id)
    plan = f'{{"suggestions": [{{"finding_id": "{f1_id}", "related_finding_id": "{f2_id}", "rationale": "x"}}]}}'
    app.dependency_overrides[get_provider] = lambda: FakeProvider(plan)
    created = (await client.post("/api/ai/correlation-suggestions", json={"target_id": asset_id})).json()
    suggestion_id = created[0]["id"]

    dismiss_response = await client.post(f"/api/ai/correlation-suggestions/{suggestion_id}/dismiss")
    assert dismiss_response.status_code == 200
    assert dismiss_response.json()["status"] == "DISMISSED"

    # Dismissing again is idempotent.
    second_dismiss = await client.post(f"/api/ai/correlation-suggestions/{suggestion_id}/dismiss")
    assert second_dismiss.status_code == 200

    accept_after_dismiss = await client.post(f"/api/ai/correlation-suggestions/{suggestion_id}/accept")
    assert accept_after_dismiss.status_code == 400


async def test_accept_unknown_suggestion_404(client):
    response = await client.post(f"/api/ai/correlation-suggestions/{uuid.uuid4()}/accept")
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Report proposal
# --------------------------------------------------------------------------


async def test_propose_report_returns_proposal(client):
    project = (await client.post("/api/projects", json={"name": "Report Proposal Fixture"})).json()
    job_id = _make_success_job(project["id"])

    plan = f'{{"title": "Nmap recon summary", "job_ids": ["{job_id}"], "rationale": "recon pass"}}'
    app.dependency_overrides[get_provider] = lambda: FakeProvider(plan)

    response = await client.post("/api/ai/reports/propose", json={"project_id": project["id"]})
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Nmap recon summary"
    assert body["job_ids"] == [job_id]


async def test_propose_report_unknown_project_404(client):
    app.dependency_overrides[get_provider] = lambda: FakeProvider('{"title": "x", "job_ids": []}')
    response = await client.post("/api/ai/reports/propose", json={"project_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_propose_report_never_creates_a_report(client):
    """Static/behavioral check: the propose route must not import
    build_report_data/render/Report -- only ever return a ReportProposal."""
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "routes" / "ai.py"
    content = source.read_text()
    assert "import build_report_data" not in content
    assert "from app.reports" not in content
    assert "Report(" not in content
