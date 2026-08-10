from app.ai.parsing import extract_json
from app.ai.prompts import ANALYST_SYSTEM, build_analysis_prompt
from app.ai.provider import AIProvider
from app.ai.schemas import AnalysisResult


class AIAnalyst:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def analyze(self, tool: str, target: str, exit_code: int | None, parsed_result: dict, stdout: str) -> AnalysisResult:
        prompt = build_analysis_prompt(tool, target, exit_code, parsed_result, stdout)
        raw = await self.provider.generate(prompt, system=ANALYST_SYSTEM, json_mode=True)

        data = extract_json(raw)
        if data is None:
            return AnalysisResult(
                risk="INFO",
                summary="AI analysis could not be parsed as structured output.",
                raw_response=raw[:2000],
            )

        try:
            return AnalysisResult.model_validate(data)
        except Exception:
            return AnalysisResult(
                risk="INFO",
                summary="AI analysis returned an unexpected shape.",
                raw_response=raw[:2000],
            )
