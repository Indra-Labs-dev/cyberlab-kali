import pytest
from pydantic import ValidationError

from app.tools import registry
from app.tools.schema import ArgumentDef, CommandDef, OutputDef, ToolDefinition, ToolProfile


def test_list_tools_includes_mvp_tools():
    names = {tool.name for tool in registry.list_tools()}
    assert {"nmap", "whatweb", "nikto"}.issubset(names)


def test_every_tool_has_a_risk_level():
    expected = {"nmap": "CAUTION", "whatweb": "SAFE", "nikto": "RESTRICTED", "sqlmap": "MANUAL_ONLY"}
    for tool in registry.list_tools():
        if tool.name in expected:
            assert tool.risk_level == expected[tool.name]
        assert tool.risk_level in ("SAFE", "CAUTION", "RESTRICTED", "MANUAL_ONLY")


def test_get_unknown_tool_raises():
    with pytest.raises(registry.ToolNotFoundError):
        registry.get_tool("metasploit")


def test_build_command_nmap_minimal():
    args = registry.build_command("nmap", {"target": "scanme.nmap.org"})
    assert args == ["-oX", "-", "-sT", "-Pn", "scanme.nmap.org"]


def test_build_command_nmap_with_flags():
    args = registry.build_command(
        "nmap",
        {"target": "10.0.0.1", "ports": "80,443", "service_detection": True},
    )
    assert args == ["-oX", "-", "-sT", "-Pn", "-p", "80,443", "-sV", "10.0.0.1"]


def test_build_command_missing_required_target():
    with pytest.raises(registry.ToolValidationError):
        registry.build_command("nmap", {})


def test_build_command_rejects_flag_injection_via_target():
    with pytest.raises(registry.ToolValidationError):
        registry.build_command("nmap", {"target": "--script=vuln"})


def test_build_command_rejects_shell_metacharacters():
    with pytest.raises(registry.ToolValidationError):
        registry.build_command("nmap", {"target": "10.0.0.1; rm -rf /"})


def test_build_command_rejects_unknown_argument():
    with pytest.raises(registry.ToolValidationError):
        registry.build_command("nmap", {"target": "10.0.0.1", "not_a_real_arg": "x"})


def test_build_command_rejects_bad_port_pattern():
    with pytest.raises(registry.ToolValidationError):
        registry.build_command("nmap", {"target": "10.0.0.1", "ports": "80;whoami"})


def test_build_command_rejects_invalid_choice():
    with pytest.raises(registry.ToolValidationError):
        registry.build_command("nmap", {"target": "10.0.0.1", "timing": "9"})


def test_build_command_nikto_uses_flag_not_positional():
    args = registry.build_command("nikto", {"target": "http://10.0.0.1"})
    # -nocheck is required, not optional -- see nikto.yaml for why (a real
    # bug found via Phase 12 end-to-end testing: without it nikto can stall
    # on a blocked update-check request until the job times out).
    assert args == ["-nocheck", "-h", "http://10.0.0.1"]


def test_build_command_whatweb():
    args = registry.build_command("whatweb", {"target": "http://10.0.0.1", "aggression": "1"})
    # -q is required, not optional -- see whatweb.yaml for why (a real bug
    # found via Phase 12 end-to-end testing: without it whatweb can exit 1
    # due to a logger race even when the scan itself succeeded).
    assert args == ["--log-json=-", "--no-errors", "-q", "-a", "1", "http://10.0.0.1"]


# --- Phase 12: profiles, ai_allowed, MANUAL_ONLY, multi-positional args ---


def test_every_tool_has_a_profile_and_ai_allowed_field():
    for tool in registry.list_tools():
        assert isinstance(tool.ai_allowed, bool)
        assert isinstance(tool.profiles, list)


def test_manual_only_risk_level_requires_ai_allowed_false():
    with pytest.raises(ValidationError):
        ToolDefinition(
            name="dangertool",
            category="web_security",
            risk_level="MANUAL_ONLY",
            ai_allowed=True,  # invalid combination
            command=CommandDef(executable="dangertool"),
            arguments=[],
            output=OutputDef(format="text", parser="none"),
        )


def test_sqlmap_is_manual_only_and_not_ai_allowed():
    tool = registry.get_tool("sqlmap")
    assert tool.risk_level == "MANUAL_ONLY"
    assert tool.ai_allowed is False


def test_build_command_with_profile_applies_profile_defaults():
    args = registry.build_command("nmap", {"target": "10.0.0.1"}, profile="quick_scan")
    assert "--top-ports" in args
    assert "100" in args


def test_build_command_profile_can_be_overridden_by_explicit_params():
    # quick_scan defaults top_ports to 100 -- an explicit param for the same
    # key should win, proving a profile is a starting point, not a lock.
    args = registry.build_command("nmap", {"target": "10.0.0.1", "top_ports": 50}, profile="quick_scan")
    assert "50" in args
    assert "100" not in args


def test_build_command_rejects_unknown_profile():
    with pytest.raises(registry.ToolValidationError):
        registry.build_command("nmap", {"target": "10.0.0.1"}, profile="does_not_exist")


def test_profile_referencing_unknown_argument_rejected_at_load_time():
    tool = ToolDefinition(
        name="badtool",
        category="utilities",
        command=CommandDef(executable="badtool"),
        arguments=[ArgumentDef(name="target", type="target", required=True, positional=True)],
        profiles=[ToolProfile(name="bad", args={"not_a_real_arg": True})],
        output=OutputDef(format="text", parser="none"),
    )
    from app.tools.registry import _validate_definition_integrity

    with pytest.raises(ValueError, match="unknown argument"):
        _validate_definition_integrity(tool)


def test_profile_presetting_the_target_argument_rejected_at_load_time():
    tool = ToolDefinition(
        name="badtool",
        category="utilities",
        command=CommandDef(executable="badtool"),
        arguments=[ArgumentDef(name="target", type="target", required=True, positional=True)],
        profiles=[ToolProfile(name="bad", args={"target": "10.0.0.1"})],
        output=OutputDef(format="text", parser="none"),
    )
    from app.tools.registry import _validate_definition_integrity

    with pytest.raises(ValueError, match="must not preset the target"):
        _validate_definition_integrity(tool)


def test_build_command_nc_supports_two_positional_arguments():
    # nc's CLI takes `host port` as two bare values -- the second positional
    # slot exists specifically for this case.
    args = registry.build_command("nc", {"target": "10.0.0.1", "port": 80})
    assert args == ["-zv", "-w", "5", "10.0.0.1", "80"]


def test_at_most_two_positional_arguments_allowed():
    tool = ToolDefinition(
        name="badtool",
        category="utilities",
        command=CommandDef(executable="badtool"),
        arguments=[
            ArgumentDef(name="a", type="target", required=True, positional=True),
            ArgumentDef(name="b", type="string", required=True, positional=True),
            ArgumentDef(name="c", type="string", required=True, positional=True),
        ],
        output=OutputDef(format="text", parser="none"),
    )
    from app.tools.registry import _validate_definition_integrity

    with pytest.raises(ValueError, match="at most two positional"):
        _validate_definition_integrity(tool)
