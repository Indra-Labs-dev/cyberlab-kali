from app.models.asset import AssetCriticality
from app.models.finding import Confidence, RiskPriority, Severity
from app.risk.calculator import RiskInputs, calculate_risk


def _inputs(**overrides) -> RiskInputs:
    defaults = dict(severity=Severity.MEDIUM, confidence=Confidence.MEDIUM)
    defaults.update(overrides)
    return RiskInputs(**defaults)


def test_no_cvss_falls_back_to_severity():
    # A known, precise CVSS (6.0) below the CRITICAL fallback approximation
    # (0.95 -> ~9.5) must score lower than the blind fallback -- proving the
    # real value is actually used rather than the fallback silently winning.
    known_lower_cvss = calculate_risk(_inputs(severity=Severity.CRITICAL, cvss_score=6.0))
    without_cvss = calculate_risk(_inputs(severity=Severity.CRITICAL, cvss_score=None))
    assert known_lower_cvss.score < without_cvss.score
    assert any("No CVSS available" in line for line in without_cvss.explanation)


def test_low_cvss_scores_lower_than_high_cvss():
    low = calculate_risk(_inputs(cvss_score=2.0))
    high = calculate_risk(_inputs(cvss_score=9.5))
    assert low.score < high.score


def test_low_epss_scores_lower_than_high_epss():
    low = calculate_risk(_inputs(cvss_score=7.0, epss_score=0.01))
    high = calculate_risk(_inputs(cvss_score=7.0, epss_score=0.95))
    assert low.score < high.score


def test_missing_epss_is_excluded_not_defaulted():
    """A missing EPSS must not silently act as if it were 0 or 0.5 -- the
    weight is redistributed to the other available signals instead."""
    missing = calculate_risk(_inputs(cvss_score=7.0, epss_score=None))
    zero = calculate_risk(_inputs(cvss_score=7.0, epss_score=0.0))
    assert missing.score != zero.score
    assert any("EPSS unknown" in line for line in missing.explanation)


def test_kev_false_scores_lower_than_kev_true():
    not_kev = calculate_risk(_inputs(cvss_score=7.0, kev=False))
    is_kev = calculate_risk(_inputs(cvss_score=7.0, kev=True))
    assert not_kev.score < is_kev.score


def test_kev_unknown_differs_from_kev_false():
    """KEV=unknown (never synced) must be treated differently from a
    confirmed KEV=false -- excluded from the weighted average rather than
    counted as "confirmed not exploited"."""
    unknown = calculate_risk(_inputs(cvss_score=7.0, kev=None))
    confirmed_false = calculate_risk(_inputs(cvss_score=7.0, kev=False))
    assert unknown.score != confirmed_false.score
    assert any("unknown" in line.lower() for line in unknown.explanation)
    assert any("not listed" in line.lower() for line in confirmed_false.explanation)


def test_kev_true_alone_does_not_force_maximum_score():
    result = calculate_risk(
        RiskInputs(
            severity=Severity.MEDIUM,
            confidence=Confidence.MEDIUM,
            kev=True,
            asset_criticality=AssetCriticality.MEDIUM,
        )
    )
    assert result.score < 100


def test_asset_low_scores_lower_than_asset_critical():
    low_asset = calculate_risk(_inputs(cvss_score=8.0, asset_criticality=AssetCriticality.LOW))
    critical_asset = calculate_risk(_inputs(cvss_score=8.0, asset_criticality=AssetCriticality.CRITICAL))
    assert low_asset.score < critical_asset.score


def test_no_asset_criticality_is_neutral():
    """No linked Asset must not be treated as LOW or CRITICAL -- neutral
    (equivalent to MEDIUM's ×1.00 multiplier)."""
    no_asset = calculate_risk(_inputs(cvss_score=8.0, asset_criticality=None))
    medium_asset = calculate_risk(_inputs(cvss_score=8.0, asset_criticality=AssetCriticality.MEDIUM))
    assert no_asset.score == medium_asset.score


def test_low_confidence_scores_lower_than_high_confidence():
    low_conf = calculate_risk(_inputs(cvss_score=8.0, confidence=Confidence.LOW))
    high_conf = calculate_risk(_inputs(cvss_score=8.0, confidence=Confidence.HIGH))
    assert low_conf.score < high_conf.score


def test_low_confidence_finding_never_reaches_maximum_even_with_extreme_signals():
    result = calculate_risk(
        RiskInputs(
            severity=Severity.CRITICAL,
            confidence=Confidence.LOW,
            cvss_score=10.0,
            epss_score=1.0,
            kev=True,
            asset_criticality=AssetCriticality.CRITICAL,
        )
    )
    assert result.score < 100


def test_completely_missing_data_still_produces_a_low_but_valid_score():
    result = calculate_risk(RiskInputs(severity=Severity.INFO, confidence=Confidence.MEDIUM))
    assert 0 <= result.score <= 100
    assert result.priority == RiskPriority.INFORMATIONAL


def test_full_combination_worked_example():
    result = calculate_risk(
        RiskInputs(
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
            cvss_score=9.8,
            cvss_version="3.1",
            epss_score=0.912,
            epss_percentile=0.98,
            kev=True,
            asset_criticality=AssetCriticality.CRITICAL,
        )
    )
    assert result.priority == RiskPriority.CRITICAL
    assert result.score >= 80
    assert len(result.explanation) == 5


def test_score_bounds_never_exceed_0_100():
    extreme = calculate_risk(
        RiskInputs(
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
            cvss_score=10.0,
            epss_score=1.0,
            kev=True,
            asset_criticality=AssetCriticality.CRITICAL,
        )
    )
    assert extreme.score <= 100

    floor = calculate_risk(
        RiskInputs(
            severity=Severity.INFO,
            confidence=Confidence.LOW,
            cvss_score=0.0,
            epss_score=0.0,
            kev=False,
            asset_criticality=AssetCriticality.LOW,
        )
    )
    assert floor.score >= 0


def test_deterministic_same_inputs_same_output():
    inputs = RiskInputs(
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        cvss_score=7.5,
        epss_score=0.3,
        kev=False,
        asset_criticality=AssetCriticality.HIGH,
    )
    first = calculate_risk(inputs)
    second = calculate_risk(inputs)
    assert first.score == second.score
    assert first.priority == second.priority
    assert first.explanation == second.explanation


def test_priority_bands_match_score_ranges():
    assert calculate_risk(_inputs(severity=Severity.INFO, cvss_score=0.5)).priority == RiskPriority.INFORMATIONAL
    assert calculate_risk(_inputs(cvss_score=10.0, epss_score=1.0, kev=True, asset_criticality=AssetCriticality.CRITICAL, confidence=Confidence.HIGH)).priority == RiskPriority.CRITICAL


def test_components_reflect_availability():
    result = calculate_risk(_inputs(cvss_score=7.0, epss_score=None, kev=None))
    by_name = {c.name: c for c in result.components}
    assert by_name["technical_severity"].available is True
    assert by_name["exploitation_probability"].available is False
    assert by_name["known_exploited"].available is False


def test_multiple_cve_scenario_uses_worst_case_via_service_not_calculator():
    # The calculator itself only ever sees one resolved cvss/epss value --
    # picking the worst among several CVEs on one finding is
    # app/risk/service.py::build_risk_inputs's job, covered in
    # tests/risk/test_service.py. This test documents that boundary.
    result = calculate_risk(_inputs(cvss_score=9.9))
    assert result.inputs.cvss_score == 9.9
