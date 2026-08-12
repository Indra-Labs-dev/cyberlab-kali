"""Phase 16 -- deterministic Finding identity. Pure functions, no I/O, no
database access -- called from app/findings/service.py at extraction time.

Two-tier strategy (see docs/phase-16-correlation-deduplication.md for the
full rationale):

1. If the finding carries one or more CVE ids, identity is
   `(asset_id, sorted CVE ids)` -- tool-independent on purpose: two
   different tools reporting the same CVE on the same asset are the same
   logical vulnerability, not two ("Rule 3" from the spec is satisfied by
   merging into one Finding here, not by a separate relation).
2. Otherwise, identity is
   `(asset_id, normalized_title, port, protocol)` -- also tool-independent,
   but in practice each extractor's title phrasing is distinct enough
   (see app/findings/extractor.py) that two different tools essentially
   never collide here; the same tool re-observing the same fact does, which
   is the primary "repeated scan" deduplication case.

`source_tool` is deliberately never part of the identity key in either
tier -- see app/findings/service.py::merge_source_tools for how provenance
(which tools contributed) is tracked separately from identity.

A Finding whose Job has no `target_id` (free-text target, no Asset) gets
signature=None and is excluded from deduplication/lifecycle/correlation
entirely -- same precedent already established by the Diff Engine
(Phase 14) and Risk Score (Phase 15).
"""

import hashlib
import re
import uuid
from urllib.parse import urlparse

# Collapses runs of whitespace and strips -- makes "Open  port  80/tcp " and
# "open port 80/tcp" produce the same signature despite trivial formatting
# differences, without attempting any semantic/fuzzy matching.
_WHITESPACE_RUN = re.compile(r"\s+")

# Tools whose parser already exposes a structured port/protocol directly on
# the finding's evidence dict (see app/tools/parsers/{nmap,masscan}.py) --
# every other tool's evidence has no such field (verified against every
# registered parser during the Phase 16 audit), so port/protocol for them
# is derived from the finding's `target` string instead (see
# extract_port_protocol below).
_EVIDENCE_PORT_TOOLS = {"nmap", "masscan"}


def normalize_title(title: str) -> str:
    """Lowercase, trim, collapse internal whitespace. Deliberately NOT a
    fuzzy/semantic normalization -- "Apache detected" and "Apache 2.4
    detected" remain different strings on purpose (see module docstring:
    cross-tool unification for non-CVE findings is Phase 16's correlation
    layer, not signature matching)."""
    return _WHITESPACE_RUN.sub(" ", title.strip().lower())


def extract_port_protocol(source_tool: str, target: str, evidence: dict) -> tuple[int | None, str | None]:
    """Best-effort, tool-aware port/protocol extraction. Returns (None, None)
    when nothing reliable can be derived -- never a guessed value.
    """
    if source_tool in _EVIDENCE_PORT_TOOLS:
        port = evidence.get("port")
        protocol = evidence.get("protocol")
        try:
            port = int(port) if port is not None else None
        except (TypeError, ValueError):
            port = None
        return (port, protocol or None) if port is not None else (None, None)

    # Every other tool: derive from the resolved target string, which is
    # either a URL (whatweb/nuclei/gobuster: "http://host:8080/") or a bare
    # "host"/"host:port" (sslscan). `urlparse` needs a netloc-style prefix
    # to parse a scheme-less "host:port" correctly -- verified interactively
    # for both shapes during the Phase 16 audit.
    if not target:
        return (None, None)
    candidate = target if "://" in target else f"//{target}"
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return (None, None)

    port = parsed.port
    if port is None:
        if parsed.scheme == "https":
            port = 443
        elif parsed.scheme == "http":
            port = 80
    return (port, "tcp") if port is not None else (None, None)


def finding_signature(
    asset_id: uuid.UUID | None,
    cve_ids: list[str],
    normalized_title: str,
    port: int | None,
    protocol: str | None,
) -> str | None:
    """Deterministic, stable, order-independent (cve_ids sorted, all parts
    joined through a fixed-position tuple rather than concatenation) SHA-256
    hex digest identifying a logical Finding. None when asset_id is None.
    """
    if asset_id is None:
        return None

    if cve_ids:
        key = ("cve", str(asset_id), ",".join(sorted({c.upper() for c in cve_ids})))
    else:
        key = ("generic", str(asset_id), normalized_title, str(port) if port is not None else "", protocol or "")

    return hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()
