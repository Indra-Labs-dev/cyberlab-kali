"""Plugin System (roadmap §8) -- app/tools/registry.py's optional second,
operator-controlled tool-definitions directory (Settings.
tool_definitions_extra_dir). Real filesystem, real YAML, real
ToolDefinition validation -- no mocking, mirroring this file's own
convention of exercising the real registry rather than a fake one.
"""

from app.core.config import get_settings
from app.tools import registry

_VALID_TOOL_YAML = """
name: {name}
category: custom
description: "A minimal plugin tool for testing."
risk_level: CAUTION
ai_allowed: true
command:
  executable: echo
output:
  format: text
  parser: none
arguments:
  - name: target
    type: target
    required: true
    positional: true
default_timeout: 30
max_timeout: 60
"""


def _reset_registry_cache():
    registry._load_definitions.cache_clear()


def test_extra_dir_unset_by_default_still_loads_exactly_the_built_in_tools(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "tool_definitions_extra_dir", "")
    _reset_registry_cache()
    try:
        names = {tool.name for tool in registry.list_tools()}
        assert len(names) == 31
        assert "nmap" in names
    finally:
        _reset_registry_cache()


def test_valid_external_tool_is_loaded_and_usable(monkeypatch, tmp_path):
    (tmp_path / "myplugin.yaml").write_text(_VALID_TOOL_YAML.format(name="myplugin"))
    settings = get_settings()
    monkeypatch.setattr(settings, "tool_definitions_extra_dir", str(tmp_path))
    _reset_registry_cache()
    try:
        tool = registry.get_tool("myplugin")
        assert tool.risk_level == "CAUTION"
        # Flows through the exact same build_command() pipeline as a
        # built-in tool -- same validation, same argument handling.
        args = registry.build_command("myplugin", {"target": "10.0.0.1"})
        assert args == ["10.0.0.1"]
        # The 31 built-in tools are still there alongside it.
        assert len(registry.list_tools()) == 32
    finally:
        _reset_registry_cache()


def test_external_tool_still_enforces_manual_only_implies_not_ai_allowed(monkeypatch, tmp_path):
    """No special-casing by origin -- a plugin author can't accidentally
    (or deliberately) skip the same schema-level safety rule a built-in
    tool must follow."""
    bad_yaml = _VALID_TOOL_YAML.format(name="badplugin").replace("risk_level: CAUTION", "risk_level: MANUAL_ONLY")
    (tmp_path / "badplugin.yaml").write_text(bad_yaml)
    settings = get_settings()
    monkeypatch.setattr(settings, "tool_definitions_extra_dir", str(tmp_path))
    _reset_registry_cache()
    try:
        # Invalid per schema (MANUAL_ONLY + ai_allowed: true) -- isolated,
        # not raised up through list_tools()/get_tool().
        names = {tool.name for tool in registry.list_tools()}
        assert "badplugin" not in names
    finally:
        _reset_registry_cache()


def test_malformed_external_file_is_isolated_not_fatal(monkeypatch, tmp_path):
    """One operator typo must never take the 31 curated tools down with
    it -- the defining safety property of this feature."""
    (tmp_path / "broken.yaml").write_text("this: [is not, valid: tool definition yaml")
    (tmp_path / "goodplugin.yaml").write_text(_VALID_TOOL_YAML.format(name="goodplugin"))
    settings = get_settings()
    monkeypatch.setattr(settings, "tool_definitions_extra_dir", str(tmp_path))
    _reset_registry_cache()
    try:
        names = {tool.name for tool in registry.list_tools()}
        assert "broken" not in names
        assert "goodplugin" in names
        assert {"nmap", "whatweb", "nikto"}.issubset(names)  # built-ins unaffected
    finally:
        _reset_registry_cache()


def test_name_colliding_with_a_built_in_tool_is_rejected(monkeypatch, tmp_path):
    """A plugin can never shadow a curated tool's real definition, even
    with an otherwise-valid file."""
    (tmp_path / "fake_nmap.yaml").write_text(_VALID_TOOL_YAML.format(name="nmap"))
    settings = get_settings()
    monkeypatch.setattr(settings, "tool_definitions_extra_dir", str(tmp_path))
    _reset_registry_cache()
    try:
        real_nmap = registry.get_tool("nmap")
        assert real_nmap.command.executable == "nmap"  # untouched, never "echo"
        assert len(registry.list_tools()) == 31  # the plugin file contributed nothing
    finally:
        _reset_registry_cache()


def test_nonexistent_extra_dir_is_silently_harmless(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tool_definitions_extra_dir", "/nonexistent/path/that/does/not/exist")
    _reset_registry_cache()
    try:
        assert len(registry.list_tools()) == 31
    finally:
        _reset_registry_cache()
