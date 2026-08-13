from app.chains.conditions import evaluate_condition, technology_tags_for_nuclei
from app.models.mission_template import ChainConditionType


def test_always_is_always_true_even_with_no_previous_result():
    assert evaluate_condition(ChainConditionType.ALWAYS, {}, None) is True


def test_non_always_condition_is_false_when_previous_result_is_none():
    assert evaluate_condition(ChainConditionType.PORT_OPEN, {"ports": [80]}, None) is False


def test_port_open_true_when_matching_port_is_open():
    result = {"hosts": [{"ports": [{"port": 80, "state": "open"}, {"port": 22, "state": "closed"}]}]}
    assert evaluate_condition(ChainConditionType.PORT_OPEN, {"ports": [80, 443]}, result) is True


def test_port_open_false_when_port_is_closed():
    result = {"hosts": [{"ports": [{"port": 80, "state": "closed"}]}]}
    assert evaluate_condition(ChainConditionType.PORT_OPEN, {"ports": [80, 443]}, result) is False


def test_port_open_false_when_port_not_in_result_at_all():
    result = {"hosts": [{"ports": [{"port": 22, "state": "open"}]}]}
    assert evaluate_condition(ChainConditionType.PORT_OPEN, {"ports": [80, 443]}, result) is False


def test_port_open_false_with_no_ports_param():
    result = {"hosts": [{"ports": [{"port": 80, "state": "open"}]}]}
    assert evaluate_condition(ChainConditionType.PORT_OPEN, {}, result) is False


def test_port_open_scans_across_multiple_hosts():
    result = {
        "hosts": [
            {"ports": [{"port": 22, "state": "open"}]},
            {"ports": [{"port": 443, "state": "open"}]},
        ]
    }
    assert evaluate_condition(ChainConditionType.PORT_OPEN, {"ports": [443]}, result) is True


def test_technology_detected_true_when_plugins_present():
    result = {"results": [{"plugins": {"Apache": {}, "PHP": {}}}]}
    assert evaluate_condition(ChainConditionType.TECHNOLOGY_DETECTED, {}, result) is True


def test_technology_detected_false_when_no_plugins():
    result = {"results": [{"plugins": {}}]}
    assert evaluate_condition(ChainConditionType.TECHNOLOGY_DETECTED, {}, result) is False


def test_technology_detected_false_with_no_results_at_all():
    assert evaluate_condition(ChainConditionType.TECHNOLOGY_DETECTED, {}, {"results": []}) is False


def test_min_severity_true_when_threshold_reached():
    result = {"findings": [{"severity": "high"}]}
    assert evaluate_condition(ChainConditionType.MIN_SEVERITY, {"min_severity": "MEDIUM"}, result) is True


def test_min_severity_true_on_exact_match():
    result = {"findings": [{"severity": "medium"}]}
    assert evaluate_condition(ChainConditionType.MIN_SEVERITY, {"min_severity": "medium"}, result) is True


def test_min_severity_false_when_below_threshold():
    result = {"findings": [{"severity": "low"}]}
    assert evaluate_condition(ChainConditionType.MIN_SEVERITY, {"min_severity": "high"}, result) is False


def test_min_severity_false_with_invalid_threshold():
    result = {"findings": [{"severity": "critical"}]}
    assert evaluate_condition(ChainConditionType.MIN_SEVERITY, {"min_severity": "not-a-severity"}, result) is False


def test_min_severity_false_with_no_findings():
    assert evaluate_condition(ChainConditionType.MIN_SEVERITY, {"min_severity": "low"}, {"findings": []}) is False


def test_technology_tags_for_nuclei_sanitizes_and_joins():
    result = {"results": [{"plugins": {"Apache": {}, "Google Font API": {}}}]}
    tags = technology_tags_for_nuclei(result)
    assert tags is not None
    assert "apache" in tags
    assert " " not in tags  # spaces stripped, matches nuclei's ^[a-z0-9,-]{1,128}$ pattern


def test_technology_tags_for_nuclei_returns_none_when_nothing_survives_sanitization():
    # A plugin name that sanitizes to an empty string (e.g. pure punctuation/emoji)
    result = {"results": [{"plugins": {"???": {}}}]}
    assert technology_tags_for_nuclei(result) is None


def test_technology_tags_for_nuclei_returns_none_with_no_technologies():
    assert technology_tags_for_nuclei({"results": []}) is None
