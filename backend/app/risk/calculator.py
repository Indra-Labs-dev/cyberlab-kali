"""Phase 15 -- CyberLab Risk Score. Pure, deterministic, no I/O: takes
already-known values in, returns a score/priority/explanation out. Never
calls a network, never asks an LLM, never touches the database. See
docs/phase-15-risk-score.md for the full derivation and worked examples.

FORMULA
-------

Three independent, evidence-based signals are combined as a *weighted
average of only the signals actually available* (never a naive sum of
incomparable scales, and never a fabricated value standing in for a
missing one):

  technical_severity  (weight 0.40) -- CVSS/10 if a CVSS score is known,
                                        else a fixed value derived from the
                                        tool-reported Severity (a rougher
                                        estimate, always available since
                                        every Finding has a severity)
  exploitation_prob   (weight 0.35) -- EPSS score (0-1), omitted entirely
                                        if unknown (not defaulted to 0 or
                                        0.5 -- see WEIGHTS_EXCLUDE_MISSING)
  known_exploited     (weight 0.25) -- 1.0 if listed in CISA KEV, 0.0 if
                                        confirmed NOT listed, omitted if KEV
                                        status has never been synced (never
                                        guessed)

  raw = sum(value_i * weight_i for available i) / sum(weight_i for available i)

Asset Criticality and Finding Confidence are always available (every Asset
has a criticality, every Finding a confidence -- neither is ever "missing"
in the way CVSS/EPSS/KEV can be), so they are applied as multiplicative
context modifiers rather than folded into the weighted average:

  criticality_multiplier: LOW=0.85  MEDIUM=1.00  HIGH=1.15  CRITICAL=1.30
                           (no linked Asset -> 1.00, neutral)
  confidence_multiplier:  LOW=0.60  MEDIUM=0.85  HIGH=1.00

  final = clamp(raw * criticality_multiplier * confidence_multiplier, 0, 1)
  score = round(final * 100), clamped to [0, 100]

Why multiply rather than add another weighted term: criticality/confidence
describe *how much this vulnerability matters here*, not *how bad the
vulnerability itself is* -- a CRITICAL asset should proportionally amplify
an already-severe finding rather than compete with CVSS/EPSS/KEV for a
fixed share of the score (see docs/phase-15-risk-score.md for the rejected
alternative of a flat additive term, and why it produced worse rankings on
worked examples).
"""

from dataclasses import dataclass, field

from app.models.asset import AssetCriticality
from app.models.finding import Confidence, RiskPriority, Severity

# --- Weights (must sum to 1.0 across whichever components are available) ---
_WEIGHT_TECHNICAL_SEVERITY = 0.40
_WEIGHT_EXPLOITATION_PROBABILITY = 0.35
_WEIGHT_KNOWN_EXPLOITED = 0.25

# CVSS-equivalent midpoints per FIRST's own qualitative severity bands
# (LOW 0.1-3.9, MEDIUM 4.0-6.9, HIGH 7.0-8.9, CRITICAL 9.0-10.0), used only
# when no actual CVSS score is available for the finding.
_SEVERITY_FALLBACK = {
    Severity.INFO: 0.00,
    Severity.LOW: 0.25,
    Severity.MEDIUM: 0.55,
    Severity.HIGH: 0.80,
    Severity.CRITICAL: 0.95,
}

_CRITICALITY_MULTIPLIER = {
    AssetCriticality.LOW: 0.85,
    AssetCriticality.MEDIUM: 1.00,
    AssetCriticality.HIGH: 1.15,
    AssetCriticality.CRITICAL: 1.30,
}

_CONFIDENCE_MULTIPLIER = {
    Confidence.LOW: 0.60,
    Confidence.MEDIUM: 0.85,
    Confidence.HIGH: 1.00,
}

# 0-19 INFORMATIONAL / 20-39 LOW / 40-59 MEDIUM / 60-79 HIGH / 80-100 CRITICAL
_PRIORITY_BANDS = (
    (80, RiskPriority.CRITICAL),
    (60, RiskPriority.HIGH),
    (40, RiskPriority.MEDIUM),
    (20, RiskPriority.LOW),
    (0, RiskPriority.INFORMATIONAL),
)


def _priority_for_score(score: int) -> RiskPriority:
    for threshold, priority in _PRIORITY_BANDS:
        if score >= threshold:
            return priority
    return RiskPriority.INFORMATIONAL


@dataclass
class RiskInputs:
    severity: Severity
    confidence: Confidence
    cvss_score: float | None = None
    cvss_version: str | None = None
    epss_score: float | None = None
    epss_percentile: float | None = None
    kev: bool | None = None  # None = unknown (never synced), not "false"
    asset_criticality: AssetCriticality | None = None  # None = no linked Asset


@dataclass
class RiskComponent:
    name: str
    value: float  # 0-1, normalized
    weight: float
    available: bool


@dataclass
class RiskResult:
    score: int  # 0-100
    priority: RiskPriority
    inputs: RiskInputs
    explanation: list[str] = field(default_factory=list)
    components: list[RiskComponent] = field(default_factory=list)
    criticality_multiplier: float = 1.0
    confidence_multiplier: float = 1.0
    raw_score: float = 0.0  # the 0-1 weighted average, before multipliers


def calculate_risk(inputs: RiskInputs) -> RiskResult:
    components: list[RiskComponent] = []

    if inputs.cvss_score is not None:
        technical_value = max(0.0, min(1.0, inputs.cvss_score / 10.0))
    else:
        technical_value = _SEVERITY_FALLBACK.get(inputs.severity, 0.0)
    components.append(
        RiskComponent("technical_severity", technical_value, _WEIGHT_TECHNICAL_SEVERITY, available=True)
    )

    if inputs.epss_score is not None:
        components.append(
            RiskComponent(
                "exploitation_probability",
                max(0.0, min(1.0, inputs.epss_score)),
                _WEIGHT_EXPLOITATION_PROBABILITY,
                available=True,
            )
        )
    else:
        components.append(RiskComponent("exploitation_probability", 0.0, _WEIGHT_EXPLOITATION_PROBABILITY, available=False))

    if inputs.kev is not None:
        components.append(
            RiskComponent("known_exploited", 1.0 if inputs.kev else 0.0, _WEIGHT_KNOWN_EXPLOITED, available=True)
        )
    else:
        components.append(RiskComponent("known_exploited", 0.0, _WEIGHT_KNOWN_EXPLOITED, available=False))

    available = [c for c in components if c.available]
    total_weight = sum(c.weight for c in available)
    raw_score = sum(c.value * c.weight for c in available) / total_weight if total_weight > 0 else 0.0

    criticality_multiplier = _CRITICALITY_MULTIPLIER.get(inputs.asset_criticality, 1.0)
    confidence_multiplier = _CONFIDENCE_MULTIPLIER.get(inputs.confidence, 0.85)

    final = raw_score * criticality_multiplier * confidence_multiplier
    final = max(0.0, min(1.0, final))
    score = max(0, min(100, round(final * 100)))
    priority = _priority_for_score(score)

    explanation = _build_explanation(inputs, criticality_multiplier, confidence_multiplier)

    return RiskResult(
        score=score,
        priority=priority,
        inputs=inputs,
        explanation=explanation,
        components=components,
        criticality_multiplier=criticality_multiplier,
        confidence_multiplier=confidence_multiplier,
        raw_score=raw_score,
    )


def _build_explanation(inputs: RiskInputs, criticality_multiplier: float, confidence_multiplier: float) -> list[str]:
    lines: list[str] = []

    if inputs.cvss_score is not None:
        version = inputs.cvss_version or "unknown version"
        lines.append(f"CVSS {inputs.cvss_score:g} ({version})")
    else:
        lines.append(f"No CVSS available — using tool-reported severity ({inputs.severity.value}) as an approximation")

    if inputs.epss_score is not None:
        pct = inputs.epss_score * 100
        if inputs.epss_score >= 0.5:
            lines.append(f"EPSS {pct:.1f}% — high probability of exploitation in the wild")
        elif inputs.epss_score >= 0.1:
            lines.append(f"EPSS {pct:.1f}% — moderate exploitation probability")
        else:
            lines.append(f"EPSS {pct:.1f}% — low exploitation probability")
    else:
        lines.append("EPSS unknown — not yet synced for this CVE, excluded from the score")

    if inputs.kev is True:
        lines.append("Listed in CISA KEV — known to be actively exploited")
    elif inputs.kev is False:
        lines.append("Not listed in CISA KEV")
    else:
        lines.append("CISA KEV status unknown — catalog not yet synced")

    if inputs.asset_criticality is not None:
        lines.append(f"Asset criticality: {inputs.asset_criticality.value} (×{criticality_multiplier:.2f})")
    else:
        lines.append("Asset criticality: unknown (finding not linked to a registered Asset)")

    lines.append(f"Finding confidence: {inputs.confidence.value} (×{confidence_multiplier:.2f})")

    return lines
