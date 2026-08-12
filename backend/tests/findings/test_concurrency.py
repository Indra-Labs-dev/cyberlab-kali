"""Mandatory real-concurrency proof for the Phase 16 upsert (see
app/findings/service.py module docstring): two independent PostgreSQL
sessions racing to create the *first* observation of a brand-new signature
must still converge on exactly one Finding row, never two. This can only be
demonstrated against a real database -- SQLite or a mocked session would
never exercise the actual unique-index collision + SAVEPOINT retry path.
"""

import threading
import uuid
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.sync_session import get_sync_session
from app.findings.service import upsert_finding
from app.main import app
from app.models.finding import Finding
from app.models.job import Job, JobStatus


async def _make_asset() -> str:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Concurrency Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()
    return asset["id"]


def _finding_data() -> dict:
    return {
        "target": "10.0.0.1",
        "source_tool": "nmap",
        "title": "Open port 80/tcp (http)",
        "description": "nmap found port 80/tcp open.",
        "severity": "INFO",
        "evidence": {"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
        "cve_ids": [],
    }


async def test_two_concurrent_sessions_racing_on_same_signature_yield_exactly_one_finding():
    asset_id = await _make_asset()

    job_ids = []
    for _ in range(2):
        session = get_sync_session()
        try:
            job = Job(
                id=uuid.uuid4(),
                tool="nmap",
                target="10.0.0.1",
                target_id=uuid.UUID(asset_id),
                params={},
                status=JobStatus.SUCCESS,
                finished_at=datetime.now(timezone.utc),
            )
            session.add(job)
            session.commit()
            job_ids.append(job.id)
        finally:
            session.close()

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    results: list[uuid.UUID] = []
    results_lock = threading.Lock()

    def worker(job_id: uuid.UUID) -> None:
        session = get_sync_session()
        try:
            job = session.get(Job, job_id)
            barrier.wait(timeout=10)  # maximize the chance both threads race the same INSERT window
            finding = upsert_finding(session, job, _finding_data())
            session.commit()
            with results_lock:
                results.append(finding.id)
        except BaseException as exc:  # noqa: BLE001 -- must surface on the main thread, not swallow
            with results_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(job_id,)) for job_id in job_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"upsert_finding raised under concurrency: {errors}"
    assert len(results) == 2
    assert results[0] == results[1]  # both threads resolved to the SAME Finding row

    session = get_sync_session()
    try:
        finding = session.get(Finding, results[0])
        assert finding.observation_count == 2
        assert set(finding.observation_job_ids) == {str(j) for j in job_ids}

        rows = session.execute(select(Finding).where(Finding.signature == finding.signature)).scalars().all()
        assert len(rows) == 1  # exactly one Finding for this signature, never two
    finally:
        session.close()
