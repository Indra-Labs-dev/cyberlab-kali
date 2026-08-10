import json

from app.reports.renderers import render

SAMPLE_DATA = {
    "title": "Test Report",
    "generated_at": "2026-08-10T00:00:00+00:00",
    "scope": {"targets": ["10.0.0.1"], "tools_used": ["nmap"]},
    "executive_summary": {"total_jobs": 1, "total_findings": 1, "by_severity": {"INFO": 1}},
    "jobs": [
        {
            "id": "job-1",
            "tool": "nmap",
            "target": "10.0.0.1",
            "status": "SUCCESS",
            "created_at": "2026-08-10T00:00:00+00:00",
            "started_at": "2026-08-10T00:00:01+00:00",
            "finished_at": "2026-08-10T00:00:02+00:00",
            "exit_code": 0,
            "ai_analysis": {"risk": "INFO", "summary": "Nothing notable."},
        }
    ],
    "findings": [
        {
            "id": "finding-1",
            "job_id": "job-1",
            "target": "10.0.0.1",
            "source_tool": "nmap",
            "title": "Open port 80/tcp (http)",
            "description": "Port 80 is open.",
            "severity": "INFO",
            "confidence": "MEDIUM",
            "evidence": {"port": 80},
            "recommendation": None,
            "created_at": "2026-08-10T00:00:00+00:00",
        }
    ],
}


def test_render_json_is_valid_and_roundtrips():
    content, is_binary = render("json", SAMPLE_DATA)
    assert is_binary is False
    parsed = json.loads(content)
    assert parsed["title"] == "Test Report"
    assert parsed["findings"][0]["severity"] == "INFO"


def test_render_markdown_contains_key_sections():
    content, is_binary = render("markdown", SAMPLE_DATA)
    assert is_binary is False
    assert "# Test Report" in content
    assert "Open port 80/tcp" in content
    assert "AI risk assessment" in content


def test_render_html_contains_findings_and_escapes_nothing_unexpected():
    content, is_binary = render("html", SAMPLE_DATA)
    assert is_binary is False
    assert "<html" in content
    assert "Open port 80/tcp" in content
    assert "10.0.0.1" in content


def test_render_html_escapes_finding_content_from_scanned_targets():
    # Finding titles/descriptions can reflect content from the scanned target
    # (tool output) -- e.g. nikto echoing a page's raw <script> tag. The HTML
    # report must escape this rather than injecting it verbatim.
    malicious_data = json.loads(json.dumps(SAMPLE_DATA))  # deep copy
    malicious_data["findings"][0]["title"] = "<script>alert(document.cookie)</script>"
    malicious_data["findings"][0]["description"] = "<img src=x onerror=alert(1)>"

    content, _ = render("html", malicious_data)

    assert "<script>alert(document.cookie)</script>" not in content
    assert "<img src=x onerror=alert(1)>" not in content
    assert "&lt;script&gt;" in content


def test_render_pdf_returns_base64_encoded_bytes():
    content, is_binary = render("pdf", SAMPLE_DATA)
    assert is_binary is True
    import base64

    raw = base64.b64decode(content)
    assert raw[:4] == b"%PDF"


def test_render_pdf_does_not_crash_on_markup_like_finding_content():
    # reportlab's Paragraph interprets a small XML-like markup subset; finding
    # content containing something that looks like markup (e.g. an unclosed
    # <b> tag reflected from a scanned page) must not break PDF generation.
    malicious_data = json.loads(json.dumps(SAMPLE_DATA))
    malicious_data["findings"][0]["title"] = "<b>unclosed bold & <font color='white'>hidden text"
    malicious_data["findings"][0]["description"] = "<script>alert(1)</script> & other <unclosed"

    content, is_binary = render("pdf", malicious_data)
    assert is_binary is True
    import base64

    raw = base64.b64decode(content)
    assert raw[:4] == b"%PDF"


def test_render_unknown_format_raises():
    import pytest

    with pytest.raises(ValueError):
        render("xml", SAMPLE_DATA)
