import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.main import app
from app.models.finding import Confidence, Finding, Severity
from app.models.job import Job, JobStatus


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_job_with_finding() -> str:
    session = get_sync_session()
    try:
        job = Job(
            id=uuid.uuid4(),
            tool="nmap",
            target="10.0.0.1",
            params={},
            status=JobStatus.SUCCESS,
            evidence_sha256="b" * 64,
        )
        session.add(job)
        session.commit()

        finding = Finding(
            job_id=job.id,
            target="10.0.0.1",
            source_tool="nmap",
            title="Open port 80/tcp",
            description="Port 80 is open.",
            severity=Severity.INFO,
            confidence=Confidence.MEDIUM,
            evidence={"port": 80},
        )
        session.add(finding)
        session.commit()
        return str(job.id)
    finally:
        session.close()


async def test_create_report_defaults_to_technical_template(client):
    job_id = _make_job_with_finding()
    response = await client.post(
        "/api/reports", json={"title": "Default Template", "job_ids": [job_id], "format": "json"}
    )
    assert response.status_code == 201
    assert response.json()["template"] == "technical"


@pytest.mark.parametrize("template", ["executive", "technical", "evidence_package"])
@pytest.mark.parametrize("fmt", ["html", "markdown", "json", "pdf"])
async def test_create_and_download_report_for_every_format_template_pair(client, fmt, template):
    job_id = _make_job_with_finding()
    create = await client.post(
        "/api/reports",
        json={"title": f"{fmt}-{template}", "job_ids": [job_id], "format": fmt, "template": template},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["format"] == fmt
    assert body["template"] == template
    report_id = body["id"]

    download = await client.get(f"/api/reports/{report_id}/download")
    assert download.status_code == 200
    assert len(download.content) > 0


async def test_create_report_with_no_matching_jobs_404s(client):
    response = await client.post(
        "/api/reports",
        json={"title": "Empty", "job_ids": [str(uuid.uuid4())], "format": "json"},
    )
    assert response.status_code == 404


async def test_get_report_roundtrips_template(client):
    job_id = _make_job_with_finding()
    create = await client.post(
        "/api/reports",
        json={"title": "Roundtrip", "job_ids": [job_id], "format": "html", "template": "evidence_package"},
    )
    report_id = create.json()["id"]

    get_response = await client.get(f"/api/reports/{report_id}")
    assert get_response.status_code == 200
    assert get_response.json()["template"] == "evidence_package"


async def test_get_nonexistent_report_404s(client):
    response = await client.get(f"/api/reports/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_reports_includes_created(client):
    job_id = _make_job_with_finding()
    await client.post("/api/reports", json={"title": "Listed Report", "job_ids": [job_id], "format": "json"})

    response = await client.get("/api/reports")
    assert response.status_code == 200
    assert any(r["title"] == "Listed Report" for r in response.json())
