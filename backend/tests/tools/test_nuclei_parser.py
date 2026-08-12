import json

from app.tools.parsers.nuclei import cvss_hints, parse_nuclei

# Real nuclei JSONL shape, verified live against nuclei v3.11.0 (Phase 15
# audit) -- cve-id is a lowercased array, cvss-metrics is the full vector
# string with the version prefix, cvss-score a float.
_REAL_LINE = json.dumps(
    {
        "template-id": "test-always-match",
        "info": {
            "name": "Test Always Match",
            "severity": "high",
            "description": "test template",
            "classification": {
                "cve-id": ["cve-2021-44228"],
                "cwe-id": ["cwe-502"],
                "cvss-metrics": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                "cvss-score": 9.8,
            },
        },
        "matched-at": "http://example/",
        "host": "example",
    }
)


def test_parse_nuclei_extracts_cve_ids_uppercased():
    result = parse_nuclei(_REAL_LINE)
    assert result["findings"][0]["cve_ids"] == ["CVE-2021-44228"]


def test_parse_nuclei_extracts_cvss_score_and_version():
    result = parse_nuclei(_REAL_LINE)
    finding = result["findings"][0]
    assert finding["cvss_score"] == 9.8
    assert finding["cvss_version"] == "3.1"
    assert finding["cvss_vector"] == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"


def test_parse_nuclei_no_classification_leaves_cve_fields_empty():
    line = json.dumps({"template-id": "t", "info": {"name": "n", "severity": "info"}, "host": "h"})
    result = parse_nuclei(line)
    finding = result["findings"][0]
    assert finding["cve_ids"] == []
    assert finding["cvss_score"] is None
    assert finding["cvss_version"] is None


def test_parse_nuclei_cvss_v4_version_not_confused_with_v3():
    line = json.dumps(
        {
            "template-id": "t",
            "info": {
                "name": "n",
                "severity": "critical",
                "classification": {"cve-id": ["cve-2024-1"], "cvss-metrics": "CVSS:4.0/AV:N/AC:L", "cvss-score": 9.2},
            },
            "host": "h",
        }
    )
    result = parse_nuclei(line)
    assert result["findings"][0]["cvss_version"] == "4.0"


def test_parse_nuclei_multiple_cves_deduplicated_and_sorted():
    line = json.dumps(
        {
            "template-id": "t",
            "info": {"name": "n", "severity": "high", "classification": {"cve-id": ["cve-2020-2", "cve-2020-1", "cve-2020-1"]}},
            "host": "h",
        }
    )
    result = parse_nuclei(line)
    assert result["findings"][0]["cve_ids"] == ["CVE-2020-1", "CVE-2020-2"]


def test_parse_nuclei_ignores_malformed_lines():
    result = parse_nuclei("not json\n" + _REAL_LINE + "\n\n")
    assert len(result["findings"]) == 1


def test_cvss_hints_extracted_from_parsed_result():
    parsed = parse_nuclei(_REAL_LINE)
    hints = cvss_hints(parsed)
    assert hints == [
        {
            "cve": "CVE-2021-44228",
            "cvss_score": 9.8,
            "cvss_version": "3.1",
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        }
    ]


def test_cvss_hints_skips_cve_without_cvss():
    line = json.dumps(
        {
            "template-id": "t",
            "info": {"name": "n", "severity": "high", "classification": {"cve-id": ["cve-2020-1"]}},
            "host": "h",
        }
    )
    parsed = parse_nuclei(line)
    assert cvss_hints(parsed) == []


def test_cvss_hints_empty_for_no_findings():
    assert cvss_hints({"findings": []}) == []
