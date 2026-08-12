"""Phase 14 -- Diff Engine. Pure functions comparing two normalized tool
results (the exact same dicts already produced by app/tools/parsers/) for
the same Asset/tool/profile, never a new result format.

Each `diff_*` function returns a list of plain dicts shaped like
`AssetChangeEvent` columns (minus asset_id/job_id/previous_job_id, filled in
by app/diff/service.py): `change_type`, `severity`, `field`, `old_value`,
`new_value`, `metadata`.

Only comparisons the current parsers can actually support are implemented.
Where the roadmap asks for something the parser doesn't provide (TLS issuer,
certificate fingerprint -- app/tools/parsers/sslscan.py only extracts
`subject`/`not_valid_after`), it is *not* faked -- documented as a limitation
in docs/phase-14-continuous-recon.md instead.
"""

from app.models.asset_change_event import ChangeType
from app.models.finding import Severity


def _change(change_type: ChangeType, severity: Severity, field: str, old_value, new_value, **metadata) -> dict:
    return {
        "change_type": change_type,
        "severity": severity,
        "field": field,
        "old_value": None if old_value is None else str(old_value),
        "new_value": None if new_value is None else str(new_value),
        "metadata": metadata,
    }


def _nmap_port_map(parsed: dict) -> dict[tuple[str, int], dict]:
    ports: dict[tuple[str, int], dict] = {}
    for host in parsed.get("hosts", []):
        for port in host.get("ports", []):
            try:
                key = (str(port.get("protocol", "tcp")), int(port["port"]))
            except (KeyError, TypeError, ValueError):
                continue
            ports[key] = port
    return ports


def diff_nmap(old: dict, new: dict) -> list[dict]:
    old_ports = _nmap_port_map(old)
    new_ports = _nmap_port_map(new)
    changes: list[dict] = []

    for key, port in new_ports.items():
        protocol, number = key
        was_open = old_ports.get(key, {}).get("state") == "open"
        is_open = port.get("state") == "open"
        field = f"port:{number}/{protocol}"
        if is_open and not was_open:
            changes.append(
                _change(
                    ChangeType.PORT_OPENED,
                    Severity.MEDIUM,
                    field,
                    old_value=None,
                    new_value=port.get("service") or "open",
                    port=number,
                    protocol=protocol,
                )
            )
        elif is_open and was_open:
            old_port = old_ports[key]
            if (old_port.get("service"), old_port.get("product"), old_port.get("version")) != (
                port.get("service"),
                port.get("product"),
                port.get("version"),
            ):
                old_desc = " ".join(filter(None, [old_port.get("service"), old_port.get("product"), old_port.get("version")]))
                new_desc = " ".join(filter(None, [port.get("service"), port.get("product"), port.get("version")]))
                changes.append(
                    _change(
                        ChangeType.SERVICE_CHANGED,
                        Severity.MEDIUM,
                        field,
                        old_value=old_desc or None,
                        new_value=new_desc or None,
                        port=number,
                        protocol=protocol,
                    )
                )

    for key, old_port in old_ports.items():
        if old_port.get("state") != "open":
            continue
        protocol, number = key
        if new_ports.get(key, {}).get("state") != "open":
            changes.append(
                _change(
                    ChangeType.PORT_CLOSED,
                    Severity.LOW,
                    f"port:{number}/{protocol}",
                    old_value=old_port.get("service") or "open",
                    new_value=None,
                    port=number,
                    protocol=protocol,
                )
            )

    return changes


def _whatweb_plugin_map(parsed: dict) -> dict[str, str]:
    """Flattens every result's plugins into {name: summary_string}. Multiple
    results (whatweb can report on redirects) are merged; a later one wins
    if the same plugin name repeats -- acceptable for a summary diff."""
    plugins: dict[str, str] = {}
    for result in parsed.get("results", []):
        for name, data in (result.get("plugins") or {}).items():
            plugins[name] = _summarize_plugin(data)
    return plugins


def _summarize_plugin(data) -> str:
    if isinstance(data, dict):
        parts = []
        for key in ("version", "string", "os"):
            value = data.get(key)
            if value:
                parts.append(",".join(value) if isinstance(value, list) else str(value))
        return " ".join(parts) if parts else "detected"
    return str(data)


def _whatweb_http_status(parsed: dict) -> int | None:
    results = parsed.get("results") or []
    return results[0].get("http_status") if results else None


def diff_whatweb(old: dict, new: dict) -> list[dict]:
    old_plugins = _whatweb_plugin_map(old)
    new_plugins = _whatweb_plugin_map(new)
    changes: list[dict] = []

    for name, summary in new_plugins.items():
        if name not in old_plugins:
            changes.append(
                _change(ChangeType.TECHNOLOGY_ADDED, Severity.INFO, f"technology:{name}", old_value=None, new_value=summary)
            )
        elif old_plugins[name] != summary:
            changes.append(
                _change(
                    ChangeType.TECHNOLOGY_CHANGED,
                    Severity.INFO,
                    f"technology:{name}",
                    old_value=old_plugins[name],
                    new_value=summary,
                )
            )
    for name, summary in old_plugins.items():
        if name not in new_plugins:
            changes.append(
                _change(ChangeType.TECHNOLOGY_REMOVED, Severity.INFO, f"technology:{name}", old_value=summary, new_value=None)
            )

    old_status = _whatweb_http_status(old)
    new_status = _whatweb_http_status(new)
    if old_status is not None and new_status is not None and old_status != new_status:
        changes.append(
            _change(ChangeType.HTTP_CHANGED, Severity.INFO, "http_status", old_value=old_status, new_value=new_status)
        )

    return changes


def _sslscan_certificates(parsed: dict) -> dict[str, dict]:
    certs: dict[str, dict] = {}
    for target in parsed.get("targets", []):
        cert = target.get("certificate")
        if cert:
            certs[target.get("host") or "?"] = cert
    return certs


def diff_sslscan(old: dict, new: dict) -> list[dict]:
    """Only `subject`/`not_valid_after` are compared -- the only certificate
    fields app/tools/parsers/sslscan.py extracts today. Issuer and
    fingerprint are NOT parsed, so a change to either is invisible here;
    documented in docs/phase-14-continuous-recon.md rather than assumed.
    """
    old_certs = _sslscan_certificates(old)
    new_certs = _sslscan_certificates(new)
    changes: list[dict] = []

    for host, new_cert in new_certs.items():
        old_cert = old_certs.get(host)
        if old_cert is None:
            continue  # first observation for this host -- no prior cert to compare against
        if old_cert.get("subject") != new_cert.get("subject"):
            changes.append(
                _change(
                    ChangeType.CERTIFICATE_CHANGED,
                    Severity.MEDIUM,
                    f"certificate.subject:{host}",
                    old_value=old_cert.get("subject"),
                    new_value=new_cert.get("subject"),
                )
            )
        if old_cert.get("not_valid_after") != new_cert.get("not_valid_after"):
            changes.append(
                _change(
                    ChangeType.CERTIFICATE_CHANGED,
                    Severity.MEDIUM,
                    f"certificate.not_valid_after:{host}",
                    old_value=old_cert.get("not_valid_after"),
                    new_value=new_cert.get("not_valid_after"),
                )
            )
    return changes


def diff_gobuster(old: dict, new: dict) -> list[dict]:
    old_paths = {r["path"]: r for r in old.get("results", []) if "path" in r}
    new_paths = {r["path"]: r for r in new.get("results", []) if "path" in r}
    changes: list[dict] = []

    for path, result in new_paths.items():
        if path not in old_paths:
            changes.append(
                _change(
                    ChangeType.OTHER,
                    Severity.INFO,
                    f"path:{path}",
                    old_value=None,
                    new_value=f"HTTP {result.get('status')}",
                    endpoint=path,
                )
            )
    for path in old_paths:
        if path not in new_paths:
            changes.append(
                _change(ChangeType.OTHER, Severity.INFO, f"path:{path}", old_value="present", new_value=None, endpoint=path)
            )
    return changes


_DIFFERS = {
    "nmap": diff_nmap,
    "whatweb": diff_whatweb,
    "sslscan": diff_sslscan,
    "gobuster": diff_gobuster,
}

#: Tools the Diff Engine can compare. Anything else is silently skipped by
#: app/diff/service.py -- not every tool's raw/unparsed output (parser:
#: "none", see docs/tools.md) is comparable in a structured way.
SUPPORTED_TOOLS = set(_DIFFERS)


def diff_results(tool: str, old: dict, new: dict) -> list[dict]:
    differ = _DIFFERS.get(tool)
    if differ is None:
        return []
    return differ(old or {}, new or {})
