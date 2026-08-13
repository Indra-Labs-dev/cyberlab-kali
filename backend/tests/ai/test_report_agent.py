import uuid
from datetime import datetime, timezone

from app.ai.agents.report import ReportAgent
from app.ai.provider import AIProvider
from app.models.job import Job, JobStatus


class FakeProvider(AIProvider):
    def __init__(self, response: str) -> None:
        self.response = response

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        return self.response


def _job(**overrides) -> Job:
    defaults = dict(
        id=uuid.uuid4(),
        tool="nmap",
        target="10.0.0.1",
        params={},
        status=JobStatus.SUCCESS,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Job(**defaults)


async def test_propose_with_no_jobs_returns_empty_proposal():
    agent = ReportAgent(FakeProvider('{"title": "x", "job_ids": []}'))
    proposal = await agent.propose("My Project", [])
    assert proposal.job_ids == []
    assert proposal.title


async def test_propose_parses_valid_response():
    job = _job()
    provider = FakeProvider(f'{{"title": "Nmap recon summary", "job_ids": ["{job.id}"], "rationale": "recon pass"}}')
    agent = ReportAgent(provider)
    proposal = await agent.propose("My Project", [job])

    assert proposal.title == "Nmap recon summary"
    assert proposal.job_ids == [job.id]


async def test_propose_strips_hallucinated_job_ids():
    job = _job()
    fake_id = uuid.uuid4()
    provider = FakeProvider(f'{{"title": "Report", "job_ids": ["{job.id}", "{fake_id}"], "rationale": ""}}')
    agent = ReportAgent(provider)
    proposal = await agent.propose("My Project", [job])

    assert proposal.job_ids == [job.id]  # fake_id was never in the provided job set


async def test_propose_falls_back_to_all_jobs_on_unparsable_response():
    job = _job()
    agent = ReportAgent(FakeProvider("not json"))
    proposal = await agent.propose("My Project", [job])

    assert proposal.job_ids == [job.id]
    assert "My Project" in proposal.title
