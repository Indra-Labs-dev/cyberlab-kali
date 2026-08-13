import uuid

from app.ai.agents.correlation import CorrelationAgent
from app.ai.provider import AIProvider
from app.models.finding import Confidence, Finding, Severity


class FakeProvider(AIProvider):
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        return self.response


def _finding(**overrides) -> Finding:
    defaults = dict(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        target="10.0.0.1",
        source_tool="whatweb",
        title="Outdated jQuery 1.7 detected",
        description="",
        severity=Severity.LOW,
        confidence=Confidence.MEDIUM,
        evidence={},
        cve_ids=[],
    )
    defaults.update(overrides)
    return Finding(**defaults)


async def test_suggest_returns_empty_for_fewer_than_two_findings():
    agent = CorrelationAgent(FakeProvider('{"suggestions": []}'))
    result = await agent.suggest([_finding()])
    assert result == []


async def test_suggest_parses_valid_suggestion():
    f1 = _finding(title="Outdated jQuery 1.7 detected")
    f2 = _finding(title="Reflected XSS on /search.php", source_tool="nuclei")
    provider = FakeProvider(
        f'{{"suggestions": [{{"finding_id": "{f1.id}", "related_finding_id": "{f2.id}", '
        f'"rationale": "outdated jQuery could enable the XSS"}}]}}'
    )
    agent = CorrelationAgent(provider)
    result = await agent.suggest([f1, f2])

    assert len(result) == 1
    assert result[0].finding_id == f1.id
    assert result[0].related_finding_id == f2.id
    assert "jQuery" in provider.last_prompt


async def test_suggest_strips_hallucinated_finding_ids():
    f1 = _finding()
    f2 = _finding()
    fake_id = uuid.uuid4()
    provider = FakeProvider(
        f'{{"suggestions": [{{"finding_id": "{fake_id}", "related_finding_id": "{f2.id}", "rationale": "x"}}]}}'
    )
    agent = CorrelationAgent(provider)
    result = await agent.suggest([f1, f2])
    assert result == []  # fake_id was never in the provided finding set


async def test_suggest_drops_self_referential_suggestion():
    f1 = _finding()
    f2 = _finding()
    provider = FakeProvider(f'{{"suggestions": [{{"finding_id": "{f1.id}", "related_finding_id": "{f1.id}"}}]}}')
    agent = CorrelationAgent(provider)
    result = await agent.suggest([f1, f2])
    assert result == []


async def test_suggest_falls_back_on_unparsable_response():
    agent = CorrelationAgent(FakeProvider("not json at all"))
    result = await agent.suggest([_finding(), _finding()])
    assert result == []
