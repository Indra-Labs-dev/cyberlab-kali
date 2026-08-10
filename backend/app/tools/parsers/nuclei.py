import json


def parse_nuclei(raw_output: str) -> dict:
    findings = []
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        info = record.get("info") or {}
        findings.append(
            {
                "template_id": record.get("template-id"),
                "name": info.get("name"),
                "severity": (info.get("severity") or "unknown").lower(),
                "matched_at": record.get("matched-at") or record.get("host"),
                "description": info.get("description"),
            }
        )
    return {"findings": findings}
