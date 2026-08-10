"""Normalizes tool-specific parsed results (see app/tools/parsers/) into a
common list of Finding-shaped dicts. Deliberately conservative about
severity: without exploitation/verification, an open port or a header hint
is INFO/LOW at most — we never claim HIGH/CRITICAL from a heuristic alone.
"""

RISKY_PLAINTEXT_SERVICES = {"ftp", "telnet", "rsh", "rlogin", "vnc"}

_NIKTO_VULN_KEYWORDS = ("xss", "sql injection", "injection", "vulnerable", "osvdb", "disclosure", "exposed")


def _finding(target: str, source_tool: str, title: str, description: str, severity: str, evidence: dict) -> dict:
    return {
        "target": target,
        "source_tool": source_tool,
        "title": title,
        "description": description,
        "severity": severity,
        "evidence": evidence,
    }


def extract_from_nmap(target: str, parsed: dict) -> list[dict]:
    findings = []
    for host in parsed.get("hosts", []):
        for port in host.get("ports", []):
            if port.get("state") != "open":
                continue
            service = port.get("service") or "unknown"
            severity = "LOW" if service in RISKY_PLAINTEXT_SERVICES else "INFO"
            findings.append(
                _finding(
                    target=target,
                    source_tool="nmap",
                    title=f"Open port {port['port']}/{port.get('protocol', 'tcp')} ({service})",
                    description=(
                        f"nmap found port {port['port']}/{port.get('protocol', 'tcp')} open on "
                        f"{host.get('address') or target}, running {service}."
                    ),
                    severity=severity,
                    evidence=port,
                )
            )
    return findings


def extract_from_whatweb(target: str, parsed: dict) -> list[dict]:
    findings = []
    for result in parsed.get("results", []):
        plugins = result.get("plugins", {})
        for plugin_name, plugin_data in plugins.items():
            findings.append(
                _finding(
                    target=target,
                    source_tool="whatweb",
                    title=f"Technology detected: {plugin_name}",
                    description=f"whatweb identified {plugin_name} on {result.get('target', target)}.",
                    severity="INFO",
                    evidence={"plugin": plugin_name, "data": plugin_data},
                )
            )
    return findings


def extract_from_masscan(target: str, parsed: dict) -> list[dict]:
    findings = []
    for host in parsed.get("hosts", []):
        for port in host.get("ports", []):
            if port.get("state") != "open":
                continue
            service = port.get("protocol") or "unknown"
            findings.append(
                _finding(
                    target=target,
                    source_tool="masscan",
                    title=f"Open port {port['port']}/{port.get('protocol', 'tcp')}",
                    description=f"masscan found port {port['port']}/{port.get('protocol', 'tcp')} open on {host.get('address') or target}.",
                    severity="INFO",
                    evidence=port,
                )
            )
    return findings


def extract_from_gobuster(target: str, parsed: dict) -> list[dict]:
    findings = []
    for result in parsed.get("results", []):
        findings.append(
            _finding(
                target=target,
                source_tool="gobuster",
                title=f"Discovered path: {result['path']} ({result['status']})",
                description=f"gobuster found {result['path']} on {target} (HTTP {result['status']}, {result['size']} bytes).",
                severity="INFO",
                evidence=result,
            )
        )
    return findings


# nuclei templates already carry a community-reviewed severity rating -- this
# is the one extractor that trusts the tool's own rating rather than
# recomputing a conservative one, since it isn't a heuristic guess.
_NUCLEI_SEVERITY_MAP = {
    "info": "INFO",
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
    "critical": "CRITICAL",
}


def extract_from_nuclei(target: str, parsed: dict) -> list[dict]:
    findings = []
    for item in parsed.get("findings", []):
        severity = _NUCLEI_SEVERITY_MAP.get(item.get("severity"), "INFO")
        findings.append(
            _finding(
                target=target,
                source_tool="nuclei",
                title=item.get("name") or item.get("template_id") or "nuclei match",
                description=item.get("description") or f"nuclei template {item.get('template_id')} matched on {item.get('matched_at') or target}.",
                severity=severity,
                evidence=item,
            )
        )
    return findings


_DEPRECATED_TLS_VERSIONS = {"SSLv2", "SSLv3", "TLS1.0", "TLS1.1"}


def extract_from_sslscan(target: str, parsed: dict) -> list[dict]:
    findings = []
    for host in parsed.get("targets", []):
        for protocol in host.get("protocols", []):
            if protocol.get("enabled") and protocol.get("version") in _DEPRECATED_TLS_VERSIONS:
                findings.append(
                    _finding(
                        target=target,
                        source_tool="sslscan",
                        title=f"Deprecated protocol enabled: {protocol['version']}",
                        description=f"{host.get('host') or target} accepts connections using {protocol['version']}, a deprecated/weak TLS version.",
                        severity="LOW",
                        evidence=protocol,
                    )
                )
        certificate = host.get("certificate")
        if certificate and certificate.get("subject"):
            findings.append(
                _finding(
                    target=target,
                    source_tool="sslscan",
                    title=f"Certificate: {certificate['subject']}",
                    description=f"Certificate presented by {host.get('host') or target}, valid until {certificate.get('not_valid_after')}.",
                    severity="INFO",
                    evidence=certificate,
                )
            )
    return findings


def extract_from_searchsploit(target: str, parsed: dict) -> list[dict]:
    findings = []
    for exploit in parsed.get("exploits", []):
        findings.append(
            _finding(
                target=target,
                source_tool="searchsploit",
                title=f"Public exploit found: {exploit.get('title')}",
                description=(
                    f"searchsploit matched a public exploit ({exploit.get('edb_id')}) for the search term "
                    f"{target!r} -- a keyword match, not a confirmed-applicable finding against a live system."
                ),
                severity="LOW",
                evidence=exploit,
            )
        )
    return findings


def extract_from_nikto(target: str, parsed: dict) -> list[dict]:
    findings = []
    for text in parsed.get("findings", []):
        lowered = text.lower()
        severity = "MEDIUM" if any(keyword in lowered for keyword in _NIKTO_VULN_KEYWORDS) else "LOW"
        findings.append(
            _finding(
                target=target,
                source_tool="nikto",
                title=text[:200],
                description=text,
                severity=severity,
                evidence={"raw": text},
            )
        )
    return findings


_EXTRACTORS = {
    "nmap": extract_from_nmap,
    "whatweb": extract_from_whatweb,
    "nikto": extract_from_nikto,
    "masscan": extract_from_masscan,
    "gobuster": extract_from_gobuster,
    "nuclei": extract_from_nuclei,
    "sslscan": extract_from_sslscan,
    "searchsploit": extract_from_searchsploit,
}


def extract_findings(tool: str, target: str, parsed_result: dict) -> list[dict]:
    extractor = _EXTRACTORS.get(tool)
    if extractor is None or not parsed_result:
        return []
    return extractor(target, parsed_result)
