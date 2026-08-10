"""Single source of truth for whether a Target may be used in an automated
job. AUTHORIZATION IS ENFORCED HERE, AT JOB CREATION -- never in the UI
alone, and never writable by the AI (see app/ai/ -- the planner only reads
target data, it has no code path that touches authorization_status).
"""

import re

from app.models.target import AuthorizationStatus, Target

# Docker Compose container names CyberLab itself creates for lab targets
# (see labmanager/docker_manager.py::_container_name) and the Kali tool
# container -- these are considered lab infrastructure, not third-party hosts.
_LAB_HOSTNAME_PATTERN = re.compile(r"^cyberlab-(lab-|kali$)")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Statuses that permit automated execution (running a job) against a target.
EXECUTABLE_STATUSES = {AuthorizationStatus.LAB, AuthorizationStatus.AUTHORIZED, AuthorizationStatus.LOCAL}


def infer_default_authorization(hostname: str | None, ip_address: str | None, url: str | None) -> AuthorizationStatus:
    """Best-effort default when a Target is created without an explicit
    authorization_status. Anything not confidently local/lab defaults to
    UNKNOWN -- the safe, non-executable default.
    """
    candidates = [c for c in (hostname, ip_address, url) if c]
    for candidate in candidates:
        stripped = candidate.split("://")[-1].split("/")[0].split(":")[0]
        if stripped in _LOCAL_HOSTS:
            return AuthorizationStatus.LOCAL
        if _LAB_HOSTNAME_PATTERN.match(stripped):
            return AuthorizationStatus.LAB
    return AuthorizationStatus.UNKNOWN


def is_executable(target: Target) -> bool:
    """UNKNOWN is treated as not authorized for automated actions by default
    (spec requirement) -- the user must explicitly set LAB/AUTHORIZED/LOCAL.
    """
    return target.authorization_status in EXECUTABLE_STATUSES
