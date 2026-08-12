import uuid

from app.findings.signature import extract_port_protocol, finding_signature, normalize_title


def test_normalize_title_lowercases_trims_and_collapses_whitespace():
    assert normalize_title("  Open   Port  80/tcp ") == "open port 80/tcp"


def test_normalize_title_distinct_strings_stay_distinct():
    # Deliberately not fuzzy -- see module docstring.
    assert normalize_title("Apache detected") != normalize_title("Apache 2.4 detected")


def test_extract_port_protocol_nmap_reads_evidence_directly():
    port, protocol = extract_port_protocol("nmap", "10.0.0.1", {"port": 80, "protocol": "tcp", "state": "open"})
    assert (port, protocol) == (80, "tcp")


def test_extract_port_protocol_nmap_missing_port_returns_none():
    port, protocol = extract_port_protocol("nmap", "10.0.0.1", {"state": "open"})
    assert (port, protocol) == (None, None)


def test_extract_port_protocol_masscan_coerces_string_port():
    port, protocol = extract_port_protocol("masscan", "10.0.0.1", {"port": "443", "protocol": "tcp"})
    assert (port, protocol) == (443, "tcp")


def test_extract_port_protocol_whatweb_derives_from_https_url():
    port, protocol = extract_port_protocol("whatweb", "https://10.0.0.1:8443/", {"plugin": "Apache"})
    assert (port, protocol) == (8443, "tcp")


def test_extract_port_protocol_whatweb_defaults_https_port():
    port, protocol = extract_port_protocol("whatweb", "https://10.0.0.1/", {"plugin": "Apache"})
    assert (port, protocol) == (443, "tcp")


def test_extract_port_protocol_whatweb_defaults_http_port():
    port, protocol = extract_port_protocol("whatweb", "http://10.0.0.1/", {"plugin": "Apache"})
    assert (port, protocol) == (80, "tcp")


def test_extract_port_protocol_sslscan_bare_host_port():
    port, protocol = extract_port_protocol("sslscan", "10.0.0.1:8443", {})
    assert (port, protocol) == (8443, "tcp")


def test_extract_port_protocol_sslscan_bare_host_no_port():
    port, protocol = extract_port_protocol("sslscan", "10.0.0.1", {})
    assert (port, protocol) == (None, None)


def test_extract_port_protocol_empty_target_returns_none():
    port, protocol = extract_port_protocol("nikto", "", {"raw": "..."})
    assert (port, protocol) == (None, None)


def test_finding_signature_none_without_asset():
    assert finding_signature(None, ["CVE-2024-1234"], "title", 80, "tcp") is None


def test_finding_signature_cve_takes_priority_over_generic_key():
    asset_id = uuid.uuid4()
    sig_a = finding_signature(asset_id, ["CVE-2024-1234"], "different title a", 80, "tcp")
    sig_b = finding_signature(asset_id, ["CVE-2024-1234"], "different title b", 443, "udp")
    assert sig_a == sig_b


def test_finding_signature_cve_order_and_case_independent():
    asset_id = uuid.uuid4()
    sig_a = finding_signature(asset_id, ["cve-2024-1234", "CVE-2024-5678"], "t", None, None)
    sig_b = finding_signature(asset_id, ["CVE-2024-5678", "CVE-2024-1234"], "t", None, None)
    assert sig_a == sig_b


def test_finding_signature_different_assets_never_collide():
    sig_a = finding_signature(uuid.uuid4(), ["CVE-2024-1234"], "t", None, None)
    sig_b = finding_signature(uuid.uuid4(), ["CVE-2024-1234"], "t", None, None)
    assert sig_a != sig_b


def test_finding_signature_generic_key_uses_title_port_protocol():
    asset_id = uuid.uuid4()
    sig_a = finding_signature(asset_id, [], "open port 80/tcp", 80, "tcp")
    sig_b = finding_signature(asset_id, [], "open port 80/tcp", 80, "tcp")
    sig_c = finding_signature(asset_id, [], "open port 443/tcp", 443, "tcp")
    assert sig_a == sig_b
    assert sig_a != sig_c


def test_finding_signature_is_deterministic_across_calls():
    asset_id = uuid.uuid4()
    sig_a = finding_signature(asset_id, ["CVE-2024-1234"], "t", None, None)
    sig_b = finding_signature(asset_id, ["CVE-2024-1234"], "t", None, None)
    assert sig_a == sig_b
    assert len(sig_a) == 64  # sha256 hex digest, matches Finding.signature String(64)
