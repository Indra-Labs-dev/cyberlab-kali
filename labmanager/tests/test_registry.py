import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import registry  # noqa: E402


def test_list_definitions_includes_dvwa():
    names = {d.name for d in registry.list_definitions()}
    assert "dvwa" in names


def test_get_unknown_definition_raises():
    with pytest.raises(registry.LabDefinitionNotFoundError):
        registry.get_definition("not-a-real-lab")


def test_dvwa_definition_has_required_fields():
    definition = registry.get_definition("dvwa")
    assert definition.image
    assert definition.internal_port == 80
