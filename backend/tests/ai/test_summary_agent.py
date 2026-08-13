import uuid
from datetime import datetime, timezone

from app.ai.agents.summary import SummaryAgent
from app.ai.provider import AIProvider
from app.models.asset import Asset, AssetCriticality, AssetType, AuthorizationStatus
from app.models.asset_change_event import AssetChangeEvent, ChangeType
from app.models.finding import Severity


class FakeProvider(AIProvider):
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None
        self.last_json_mode: bool | None = None

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        self.last_json_mode = json_mode
        return self.response


def _asset(**overrides) -> Asset:
    defaults = dict(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="dvwa",
        hostname="cyberlab-lab-dvwa",
        type=AssetType.CONTAINER,
        criticality=AssetCriticality.MEDIUM,
        authorization_status=AuthorizationStatus.LAB,
    )
    defaults.update(overrides)
    return Asset(**defaults)


def _change(**overrides) -> AssetChangeEvent:
    defaults = dict(
        id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        change_type=ChangeType.PORT_OPENED,
        severity=Severity.MEDIUM,
        field="port:8080/tcp",
        old_value=None,
        new_value="open",
        detected_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return AssetChangeEvent(**defaults)


async def test_summarize_with_no_assets_returns_plain_statement():
    agent = SummaryAgent(FakeProvider("should never be called"))
    text = await agent.summarize("Empty Project", [], {}, [])
    assert "Empty Project" in text
    assert "no tracked assets" in text


async def test_summarize_calls_provider_in_non_json_mode_and_returns_text():
    provider = FakeProvider("This project tracks one lab asset with no notable findings.")
    agent = SummaryAgent(provider)
    text = await agent.summarize("My Project", [_asset()], {"MEDIUM": 1}, [_change()])

    assert text == "This project tracks one lab asset with no notable findings."
    assert provider.last_json_mode is False
    assert "My Project" in provider.last_prompt
    assert "dvwa" in provider.last_prompt


async def test_summarize_truncates_an_overlong_response():
    provider = FakeProvider("x" * 5000)
    agent = SummaryAgent(provider)
    text = await agent.summarize("My Project", [_asset()], {}, [])
    assert len(text) == 2000


async def test_summarize_falls_back_on_empty_response():
    provider = FakeProvider("   ")
    agent = SummaryAgent(provider)
    text = await agent.summarize("My Project", [_asset()], {}, [])
    assert "My Project" in text
    assert "no summary available" in text
