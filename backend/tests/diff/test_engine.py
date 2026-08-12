from app.diff.engine import diff_gobuster, diff_nmap, diff_results, diff_sslscan, diff_whatweb
from app.models.asset_change_event import ChangeType


def _port(port, state="open", service=None, product=None, version=None, protocol="tcp"):
    return {"port": port, "protocol": protocol, "state": state, "service": service, "product": product, "version": version}


def test_diff_nmap_detects_new_port():
    old = {"hosts": [{"address": "1.2.3.4", "ports": [_port(80, service="http")]}]}
    new = {"hosts": [{"address": "1.2.3.4", "ports": [_port(80, service="http"), _port(8080, service="http-alt")]}]}
    changes = diff_nmap(old, new)
    assert len(changes) == 1
    assert changes[0]["change_type"] == ChangeType.PORT_OPENED
    assert changes[0]["field"] == "port:8080/tcp"
    assert changes[0]["metadata"]["port"] == 8080


def test_diff_nmap_detects_closed_port():
    old = {"hosts": [{"address": "1.2.3.4", "ports": [_port(443, service="https")]}]}
    new = {"hosts": [{"address": "1.2.3.4", "ports": []}]}
    changes = diff_nmap(old, new)
    assert len(changes) == 1
    assert changes[0]["change_type"] == ChangeType.PORT_CLOSED
    assert changes[0]["field"] == "port:443/tcp"


def test_diff_nmap_detects_service_version_change():
    old = {"hosts": [{"ports": [_port(80, service="http", product="nginx", version="1.18")]}]}
    new = {"hosts": [{"ports": [_port(80, service="http", product="nginx", version="1.20")]}]}
    changes = diff_nmap(old, new)
    assert len(changes) == 1
    assert changes[0]["change_type"] == ChangeType.SERVICE_CHANGED
    assert "1.18" in changes[0]["old_value"]
    assert "1.20" in changes[0]["new_value"]


def test_diff_nmap_no_changes_when_identical():
    result = {"hosts": [{"ports": [_port(80, service="http")]}]}
    assert diff_nmap(result, result) == []


def test_diff_nmap_closed_then_reopened_port_not_double_counted():
    # a port that was never open in `old` and is closed in `new` is not a change
    old = {"hosts": [{"ports": [_port(80, state="closed", service=None)]}]}
    new = {"hosts": [{"ports": [_port(80, state="closed", service=None)]}]}
    assert diff_nmap(old, new) == []


def test_diff_whatweb_detects_added_and_removed_technology():
    old = {"results": [{"http_status": 200, "plugins": {"Apache": {"version": ["2.4"]}}}]}
    new = {"results": [{"http_status": 200, "plugins": {"nginx": {"version": ["1.18"]}}}]}
    changes = diff_whatweb(old, new)
    types = {c["change_type"] for c in changes}
    assert ChangeType.TECHNOLOGY_ADDED in types
    assert ChangeType.TECHNOLOGY_REMOVED in types


def test_diff_whatweb_detects_version_change_as_technology_changed():
    old = {"results": [{"http_status": 200, "plugins": {"nginx": {"version": ["1.18"]}}}]}
    new = {"results": [{"http_status": 200, "plugins": {"nginx": {"version": ["1.20"]}}}]}
    changes = diff_whatweb(old, new)
    assert len(changes) == 1
    assert changes[0]["change_type"] == ChangeType.TECHNOLOGY_CHANGED
    assert changes[0]["field"] == "technology:nginx"


def test_diff_whatweb_detects_http_status_change():
    old = {"results": [{"http_status": 200, "plugins": {}}]}
    new = {"results": [{"http_status": 302, "plugins": {}}]}
    changes = diff_whatweb(old, new)
    assert len(changes) == 1
    assert changes[0]["change_type"] == ChangeType.HTTP_CHANGED
    assert changes[0]["old_value"] == "200"
    assert changes[0]["new_value"] == "302"


def test_diff_whatweb_no_changes_when_identical():
    result = {"results": [{"http_status": 200, "plugins": {"nginx": {"version": ["1.18"]}}}]}
    assert diff_whatweb(result, result) == []


def test_diff_sslscan_detects_certificate_subject_change():
    old = {"targets": [{"host": "x", "certificate": {"subject": "CN=old.example", "not_valid_after": "2030"}}]}
    new = {"targets": [{"host": "x", "certificate": {"subject": "CN=new.example", "not_valid_after": "2030"}}]}
    changes = diff_sslscan(old, new)
    assert len(changes) == 1
    assert changes[0]["change_type"] == ChangeType.CERTIFICATE_CHANGED
    assert changes[0]["field"] == "certificate.subject:x"


def test_diff_sslscan_detects_expiry_change():
    old = {"targets": [{"host": "x", "certificate": {"subject": "CN=x", "not_valid_after": "2030-01-01"}}]}
    new = {"targets": [{"host": "x", "certificate": {"subject": "CN=x", "not_valid_after": "2031-01-01"}}]}
    changes = diff_sslscan(old, new)
    assert len(changes) == 1
    assert changes[0]["field"] == "certificate.not_valid_after:x"


def test_diff_sslscan_first_observation_is_not_a_change():
    # no prior cert for this host -- nothing to compare against
    old = {"targets": []}
    new = {"targets": [{"host": "x", "certificate": {"subject": "CN=x", "not_valid_after": "2030"}}]}
    assert diff_sslscan(old, new) == []


def test_diff_gobuster_detects_new_and_removed_endpoint():
    old = {"results": [{"path": "/admin", "status": 200, "size": 10}]}
    new = {"results": [{"path": "/backup", "status": 200, "size": 5}]}
    changes = diff_gobuster(old, new)
    types = {c["change_type"] for c in changes}
    assert types == {ChangeType.OTHER}
    fields = {c["field"] for c in changes}
    assert fields == {"path:/admin", "path:/backup"}


def test_diff_results_dispatches_by_tool_name():
    old = {"hosts": [{"ports": [_port(80)]}]}
    new = {"hosts": [{"ports": [_port(80), _port(443)]}]}
    changes = diff_results("nmap", old, new)
    assert len(changes) == 1


def test_diff_results_unsupported_tool_returns_empty():
    assert diff_results("nikto", {"a": 1}, {"a": 2}) == []


def test_diff_results_handles_none_gracefully():
    assert diff_results("nmap", None, None) == []
