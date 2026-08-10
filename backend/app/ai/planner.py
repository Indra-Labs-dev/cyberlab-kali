from app.ai.parsing import extract_json
from app.ai.prompts import PLANNER_SYSTEM, build_planner_prompt
from app.ai.provider import AIProvider
from app.ai.schemas import MissionPlan, MissionStep
from app.tools import registry


class AIMissionPlanner:
    """Proposes a plan of tool runs for the user to review — never executes
    anything itself. Every step is grounded in the actual Tool Registry so
    the model can't propose a tool CyberLab doesn't have.
    """

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def plan(self, target: str, goal: str) -> MissionPlan:
        available_tools = [tool.model_dump() for tool in registry.list_tools()]
        prompt = build_planner_prompt(target, goal, available_tools)
        raw = await self.provider.generate(prompt, system=PLANNER_SYSTEM, json_mode=True)

        data = extract_json(raw)
        if data is None or "steps" not in data:
            return MissionPlan(goal=goal, target=target, raw_response=raw[:2000])

        known_tools = {tool.name for tool in registry.list_tools()}
        steps = []
        for raw_step in data.get("steps", []):
            try:
                step = MissionStep.model_validate(raw_step)
            except Exception:
                continue
            if step.tool is not None and step.tool not in known_tools:
                # The model hallucinated a tool that isn't registered — drop
                # the tool reference rather than silently trusting it.
                step.tool = None
            steps.append(step)

        return MissionPlan(goal=goal, target=target, steps=steps)
