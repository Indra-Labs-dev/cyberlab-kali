import httpx

from app.ai.provider import AIProvider
from app.core.config import get_settings


class OllamaUnavailableError(RuntimeError):
    pass


class OllamaProvider(AIProvider):
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.ollama_url
        self.model = model or settings.ollama_model

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(f"Ollama unreachable at {self.base_url}: {exc}") from exc

        return response.json().get("response", "")
