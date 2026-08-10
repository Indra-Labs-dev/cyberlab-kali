from app.ai.planner import AIMissionPlanner
from app.ai.provider import AIProvider


class FakeProvider(AIProvider):
    def __init__(self, response: str) -> None:
        self.response = response

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        return self.response


async def test_plan_parses_valid_steps():
    provider = FakeProvider(
        '{"steps": [{"label": "Port scan", "tool": "nmap", "target": "10.0.0.1", '
        '"options": {"ports": "1-1024"}, "rationale": "identify open services"}]}'
    )
    planner = AIMissionPlanner(provider)
    plan = await planner.plan("10.0.0.1", "find open web services")

    assert plan.target == "10.0.0.1"
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "nmap"
    assert plan.steps[0].options == {"ports": "1-1024"}


async def test_plan_strips_hallucinated_tool_names():
    provider = FakeProvider('{"steps": [{"label": "Exploit it", "tool": "metasploit", "target": "10.0.0.1"}]}')
    planner = AIMissionPlanner(provider)
    plan = await planner.plan("10.0.0.1", "break in")

    assert len(plan.steps) == 1
    assert plan.steps[0].tool is None  # metasploit isn't a registered tool


async def test_plan_falls_back_on_unparsable_response():
    provider = FakeProvider("I don't understand the request.")
    planner = AIMissionPlanner(provider)
    plan = await planner.plan("10.0.0.1", "do something")

    assert plan.steps == []
    assert plan.raw_response is not None
