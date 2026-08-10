from app.findings.extractor import extract_findings

NMAP_PARSED = {
    "hosts": [
        {
            "address": "10.0.0.1",
            "hostname": None,
            "state": "up",
            "ports": [
                {"port": 80, "protocol": "tcp", "state": "open", "service": "http", "product": None, "version": None},
                {"port": 21, "protocol": "tcp", "state": "open", "service": "ftp", "product": None, "version": None},
                {"port": 443, "protocol": "tcp", "state": "closed", "service": "https", "product": None, "version": None},
            ],
        }
    ]
}

WHATWEB_PARSED = {
    "results": [
        {"target": "http://10.0.0.1", "http_status": 200, "plugins": {"HTTPServer": {"string": ["nginx"]}}}
    ]
}

NIKTO_PARSED = {
    "target_ip": "10.0.0.1",
    "target_hostname": "10.0.0.1",
    "findings": [
        "Server: nginx",
        "OSVDB-3092: /admin/: This might be interesting.",
    ],
}


def test_extract_from_nmap_only_open_ports():
    findings = extract_findings("nmap", "10.0.0.1", NMAP_PARSED)
    assert len(findings) == 2  # port 443 is closed, excluded
    ports = {f["evidence"]["port"] for f in findings}
    assert ports == {80, 21}


def test_extract_from_nmap_flags_risky_plaintext_service():
    findings = extract_findings("nmap", "10.0.0.1", NMAP_PARSED)
    ftp_finding = next(f for f in findings if f["evidence"]["port"] == 21)
    http_finding = next(f for f in findings if f["evidence"]["port"] == 80)
    assert ftp_finding["severity"] == "LOW"
    assert http_finding["severity"] == "INFO"


def test_extract_from_whatweb():
    findings = extract_findings("whatweb", "http://10.0.0.1", WHATWEB_PARSED)
    assert len(findings) == 1
    assert findings[0]["severity"] == "INFO"
    assert "HTTPServer" in findings[0]["title"]


def test_extract_from_nikto_flags_osvdb_as_medium():
    findings = extract_findings("nikto", "10.0.0.1", NIKTO_PARSED)
    assert len(findings) == 2
    server_finding = next(f for f in findings if "Server:" in f["title"])
    osvdb_finding = next(f for f in findings if "OSVDB" in f["title"])
    assert server_finding["severity"] == "LOW"
    assert osvdb_finding["severity"] == "MEDIUM"


def test_extract_unknown_tool_returns_empty():
    assert extract_findings("unknown-tool", "10.0.0.1", {"anything": True}) == []


def test_extract_empty_result_returns_empty():
    assert extract_findings("nmap", "10.0.0.1", {}) == []
