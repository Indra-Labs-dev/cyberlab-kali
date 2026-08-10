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
        all_tools = registry.list_tools()
        # ai_allowed=False tools (sqlmap, and anything else marked
        # MANUAL_ONLY/high-risk) are never even shown to the model -- it
        # can't propose what it's never told exists.
        ai_visible_tools = [tool for tool in all_tools if tool.ai_allowed]
        available_tools = [tool.model_dump() for tool in ai_visible_tools]
        prompt = build_planner_prompt(target, goal, available_tools, authorization_status)
        raw = await self.provider.generate(prompt, system=PLANNER_SYSTEM, json_mode=True)

        data = extract_json(raw)
        if data is None or "steps" not in data:
            return MissionPlan(goal=goal, target=target, target_id=target_id, raw_response=raw[:2000])

        # Second, independent check: even though ai_allowed=False tools were
        # never in the prompt, a model can still emit a name it knows from
        # training data (e.g. "sqlmap") without having been told about it.
        # Never trust the prompt alone to be the enforcement -- re-validate
        # every proposed tool name against the same ai_allowed set here.
        ai_allowed_tools = {tool.name: tool for tool in ai_visible_tools}
        steps = []
        for raw_step in data.get("steps", []):
            try:
                step = MissionStep.model_validate(raw_step)
            except Exception:
                continue
            if step.tool is not None and step.tool not in ai_allowed_tools:
                # Either unregistered entirely, or registered but not
                # ai_allowed -- both cases are dropped the same way, never
                # silently trusted.
                step.tool = None
                step.profile = None
            elif step.profile is not None:
                # Same treatment for the profile name: only trust it if it
                # actually exists on this tool, otherwise fall back to None
                # (raw options) rather than passing through an invented name.
                valid_profiles = {p.name for p in ai_allowed_tools[step.tool].profiles}
                if step.profile not in valid_profiles:
                    step.profile = None
            # target_id is always assigned here, server-side, from the
            # request's resolved Target — never from anything the model
            # output. This is what lets the frontend run a step through the
            # same authorization-enforced job-creation path as everything else.
            step.target_id = target_id
            steps.append(step)

        return MissionPlan(goal=goal, target=target, target_id=target_id, steps=steps)
