"""Phase 21 -- condition evaluation for Tool Orchestrator chain steps.
Deliberately simple: three fixed condition types, no branching DSL (see
docs/roadmap.md's own explicit instruction -- "plutot qu'un DSL de
branchement complet"). Each condition is evaluated against the raw,
already-parsed `result` dict of the immediately preceding step's Job --
never re-parses stdout, never queries Finding rows (the previous step's
own commit already made its `result` available).
"""

import re

from app.assets.activity import technologies_from_whatweb
from app.models.mission_template import ChainConditionType

# Nuclei's own severities are lowercase strings in its parsed output
# (app/tools/parsers/nuclei.py::parse_nuclei), unlike the uppercase
# Finding.Severity enum -- this table is deliberately separate from
# app/risk/calculator.py::_SEVERITY_FALLBACK, which is keyed on the
# uppercase enum and serves an unrelated purpose (CVSS-equivalent scoring
# for the Risk Score, Phase 15).
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# nuclei's own registered `tags` argument pattern
# (backend/app/tools/definitions/nuclei.yaml) -- anything outside this
# character set is stripped, never passed through raw.
_NUCLEI_TAG_CHAR_RE = re.compile(r"[^a-z0-9\-]")


def _port_open(result: dict, params: dict) -> bool:
    wanted_ports = {int(p) for p in params.get("ports", [])}
    if not wanted_ports:
        return False
    for host in result.get("hosts", []):
        for port in host.get("ports", []):
            if port.get("state") == "open" and port.get("port") in wanted_ports:
                return True
    return False


def _technology_detected(result: dict) -> bool:
    return len(technologies_from_whatweb(result)) > 0


def _min_severity_reached(result: dict, params: dict) -> bool:
    threshold_rank = _SEVERITY_RANK.get(str(params.get("min_severity", "")).lower())
    if threshold_rank is None:
        return False
    for finding in result.get("findings", []):
        rank = _SEVERITY_RANK.get(str(finding.get("severity", "")).lower())
        if rank is not None and rank >= threshold_rank:
            return True
    return False


def evaluate_condition(
    condition_type: ChainConditionType, condition_params: dict, previous_result: dict | None
) -> bool:
    """`previous_result` is the immediately preceding ChainRunStep's Job.result
    -- None only if that Job somehow has no result (shouldn't happen for a
    step already reconciled to SUCCESS, but treated as "condition not met"
    rather than raising, matching this module's overall bias toward safe
    stops over crashes).
    """
    if condition_type == ChainConditionType.ALWAYS:
        return True
    if previous_result is None:
        return False
    if condition_type == ChainConditionType.PORT_OPEN:
        return _port_open(previous_result, condition_params)
    if condition_type == ChainConditionType.TECHNOLOGY_DETECTED:
        return _technology_detected(previous_result)
    if condition_type == ChainConditionType.MIN_SEVERITY:
        return _min_severity_reached(previous_result, condition_params)
    return False


def technology_tags_for_nuclei(previous_result: dict) -> str | None:
    """Best-effort auto-population of nuclei's `tags` argument from the
    technologies a preceding whatweb step detected -- the one narrow,
    literal case the roadmap names explicitly ("filtre sur les tags
    pertinents"), not a general templating mechanism: only ever applied by
    the caller (app/chains/service.py) when the *next* step is nuclei,
    its own gating condition is TECHNOLOGY_DETECTED, and its `options`
    don't already specify `tags`. Names that don't survive sanitization
    against nuclei's registered pattern are dropped; returns None (not a
    raised error) if nothing valid remains, so the caller can fall back to
    running nuclei unfiltered rather than skip the step entirely.
    """
    cleaned: list[str] = []
    for name in technologies_from_whatweb(previous_result):
        sanitized = _NUCLEI_TAG_CHAR_RE.sub("", name.lower())
        if sanitized:
            cleaned.append(sanitized)
    if not cleaned:
        return None
    return ",".join(dict.fromkeys(cleaned))[:128]  # de-dup, preserve order, respect the 128-char pattern limit
