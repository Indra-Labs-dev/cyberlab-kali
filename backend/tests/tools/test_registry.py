import pytest

from app.tools import registry


def test_list_tools_includes_mvp_tools():
    names = {tool.name for tool in registry.list_tools()}
    assert {"nmap", "whatweb", "nikto"}.issubset(names)


def test_get_unknown_tool_raises():
    with pytest.raises(registry.ToolNotFoundError):
        registry.get_tool("metasploit")


def test_build_command_nmap_minimal():
    args = registry.build_command("nmap", {"target": "scanme.nmap.org"})
    assert args == ["-oX", "-", "-sT", "scanme.nmap.org"]


def test_build_command_nmap_with_flags():
    args = registry.build_command(
        "nmap",
        {"target": "10.0.0.1", "ports": "80,443", "service_detection": True},
    )
    assert args == ["-oX", "-", "-sT", "-p", "80,443", "-sV", "10.0.0.1"]


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
    assert args == ["-Format", "txt", "-output", "-", "-h", "http://10.0.0.1"]


def test_build_command_whatweb():
    args = registry.build_command("whatweb", {"target": "http://10.0.0.1", "aggression": "1"})
    assert args == ["--log-json=-", "--no-errors", "-a", "1", "http://10.0.0.1"]
