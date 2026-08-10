from abc import ABC, abstractmethod


class AIProvider(ABC):
    """Abstraction over the underlying LLM backend so CyberLab can swap
    models/providers later without touching analyst.py / planner.py.
    """

    @abstractmethod
    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        """Return the raw text completion for `prompt`."""
        raise NotImplementedError
