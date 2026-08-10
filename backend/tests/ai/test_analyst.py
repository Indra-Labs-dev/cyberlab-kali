from app.ai.analyst import AIAnalyst
from app.ai.provider import AIProvider


class FakeProvider(AIProvider):
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        self.last_system = system
        return self.response


async def test_analyze_parses_valid_response():
    provider = FakeProvider(
        '{"risk": "HIGH", "summary": "Open admin port", "findings": ["port 8080 open"], '
        '"recommendations": ["restrict access"], "next_steps": ["run whatweb"]}'
    )
    analyst = AIAnalyst(provider)
    result = await analyst.analyze("nmap", "10.0.0.1", 0, {"hosts": []}, "some output")

    assert result.risk == "HIGH"
    assert result.summary == "Open admin port"
    assert result.findings == ["port 8080 open"]
    assert "10.0.0.1" in provider.last_prompt


async def test_analyze_falls_back_gracefully_on_unparsable_response():
    provider = FakeProvider("I'm not sure how to help with that.")
    analyst = AIAnalyst(provider)
    result = await analyst.analyze("nmap", "10.0.0.1", 0, {}, "")

    assert result.risk == "INFO"
    assert result.raw_response is not None


async def test_analyze_falls_back_on_wrong_shape():
    provider = FakeProvider('{"unexpected": "shape"}')
    analyst = AIAnalyst(provider)
    result = await analyst.analyze("nmap", "10.0.0.1", 0, {}, "")

    # unknown keys are ignored by pydantic; missing keys use schema defaults
    assert result.risk == "INFO"
