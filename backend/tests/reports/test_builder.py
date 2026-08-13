import uuid

import pytest

from app.db.session import async_session_factory
from app.db.sync_session import get_sync_session
from app.models.job import Job, JobStatus
from app.reports.builder import NoJobsFoundError, build_report_data


def _make_job(evidence_sha256: str | None) -> str:
    session = get_sync_session()
    try:
        job = Job(
            id=uuid.uuid4(),
            tool="nmap",
            target="10.0.0.1",
            params={},
            status=JobStatus.SUCCESS,
            evidence_sha256=evidence_sha256,
        )
        session.add(job)
        session.commit()
        return str(job.id)
    finally:
        session.close()


async def test_build_report_data_includes_evidence_sha256_when_present():
    job_id = _make_job("c" * 64)
    async with async_session_factory() as db:
        data = await build_report_data(db, [uuid.UUID(job_id)], "Title")
    assert data["jobs"][0]["evidence_sha256"] == "c" * 64


async def test_build_report_data_evidence_sha256_is_none_when_job_never_ran():
    job_id = _make_job(None)
    async with async_session_factory() as db:
        data = await build_report_data(db, [uuid.UUID(job_id)], "Title")
    assert data["jobs"][0]["evidence_sha256"] is None


async def test_build_report_data_raises_when_no_jobs_match():
    async with async_session_factory() as db:
        with pytest.raises(NoJobsFoundError):
            await build_report_data(db, [uuid.uuid4()], "Title")
