import re

_META_PREFIXES = ("Target IP", "Target Hostname", "Target Port", "Start Time", "End Time")
_SUMMARY_PATTERN = re.compile(r"^\d+ requests:")


def parse_nikto(raw_output: str) -> dict:
    target_ip = None
    target_hostname = None
    findings = []

    for line in raw_output.splitlines():
        line = line.strip()
        if not line.startswith("+ "):
            continue
        content = line[2:].strip()

        if content.startswith("Target IP:"):
            target_ip = content.split(":", 1)[1].strip()
            continue
        if content.startswith("Target Hostname:"):
            target_hostname = content.split(":", 1)[1].strip()
            continue
        if content.startswith(_META_PREFIXES) or _SUMMARY_PATTERN.match(content):
            continue

        findings.append(content)

    return {
        "target_ip": target_ip,
        "target_hostname": target_hostname,
        "findings": findings,
    }
