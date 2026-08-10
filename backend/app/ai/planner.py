import uuid

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

    async def plan(
        self,
        target: str,
        goal: str,
        target_id: uuid.UUID | None = None,
        authorization_status: str | None = None,
    ) -> MissionPlan:
        available_tools = [tool.model_dump() for tool in registry.list_tools()]
        prompt = build_planner_prompt(target, goal, available_tools, authorization_status)
        raw = await self.provider.generate(prompt, system=PLANNER_SYSTEM, json_mode=True)

        data = extract_json(raw)
        if data is None or "steps" not in data:
            return MissionPlan(goal=goal, target=target, target_id=target_id, raw_response=raw[:2000])

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
            # target_id is always assigned here, server-side, from the
            # request's resolved Target — never from anything the model
            # output. This is what lets the frontend run a step through the
            # same authorization-enforced job-creation path as everything else.
            step.target_id = target_id
            steps.append(step)

        return MissionPlan(goal=goal, target=target, target_id=target_id, steps=steps)
