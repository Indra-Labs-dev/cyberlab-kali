from functools import lru_cache
from pathlib import Path

import yaml

from schema import LabDefinition

DEFINITIONS_DIR = Path(__file__).parent / "definitions"


class LabDefinitionNotFoundError(LookupError):
    pass


@lru_cache
def _load_definitions() -> dict[str, LabDefinition]:
    definitions: dict[str, LabDefinition] = {}
    for path in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        definition = LabDefinition.model_validate(raw)
        definitions[definition.name] = definition
    return definitions


def list_definitions() -> list[LabDefinition]:
    return list(_load_definitions().values())


def get_definition(name: str) -> LabDefinition:
    try:
        return _load_definitions()[name]
    except KeyError as exc:
        raise LabDefinitionNotFoundError(f"unknown lab definition: {name}") from exc
