import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import CANDIDATE_TOOLS, _parse_extra_tools  # noqa: E402


def test_empty_raw_returns_nothing():
    assert _parse_extra_tools("", CANDIDATE_TOOLS) == {}


def test_single_entry_parsed():
    assert _parse_extra_tools("mytool:mytool-bin", CANDIDATE_TOOLS) == {"mytool": "mytool-bin"}


def test_multiple_entries_parsed():
    result = _parse_extra_tools("a:a-bin,b:b-bin", CANDIDATE_TOOLS)
    assert result == {"a": "a-bin", "b": "b-bin"}


def test_whitespace_around_entries_and_separators_is_stripped():
    assert _parse_extra_tools(" mytool : mytool-bin , other:other-bin ", CANDIDATE_TOOLS) == {
        "mytool": "mytool-bin",
        "other": "other-bin",
    }


def test_malformed_entry_without_colon_is_skipped_not_raised():
    assert _parse_extra_tools("not-a-valid-entry", CANDIDATE_TOOLS) == {}


def test_entry_with_empty_name_or_executable_is_skipped():
    assert _parse_extra_tools(":no-name", CANDIDATE_TOOLS) == {}
    assert _parse_extra_tools("no-executable:", CANDIDATE_TOOLS) == {}


def test_blank_entries_between_commas_are_ignored():
    assert _parse_extra_tools("mytool:mytool-bin,,  ,other:other-bin", CANDIDATE_TOOLS) == {
        "mytool": "mytool-bin",
        "other": "other-bin",
    }


def test_name_colliding_with_a_curated_tool_is_rejected():
    """A typo in EXTRA_ALLOWED_TOOLS must never be able to shadow a
    curated tool's already-resolved path."""
    assert "nmap" in CANDIDATE_TOOLS
    result = _parse_extra_tools("nmap:something-else,mytool:mytool-bin", CANDIDATE_TOOLS)
    assert "nmap" not in result
    assert result == {"mytool": "mytool-bin"}


def test_only_genuinely_resolvable_binaries_end_up_allowed():
    """Mirrors the real ALLOWED_TOOLS construction: a plugin entry naming
    a binary that isn't actually on PATH must never become runnable."""
    import shutil

    extra = _parse_extra_tools("realbin:cat,fakebin:this-binary-does-not-exist-anywhere", CANDIDATE_TOOLS)
    resolved = {name: shutil.which(executable) for name, executable in extra.items()}
    assert resolved["realbin"] is not None
    assert resolved["fakebin"] is None
