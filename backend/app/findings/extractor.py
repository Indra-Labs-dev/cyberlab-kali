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
}


def extract_findings(tool: str, target: str, parsed_result: dict) -> list[dict]:
    extractor = _EXTRACTORS.get(tool)
    if extractor is None or not parsed_result:
        return []
    return extractor(target, parsed_result)
