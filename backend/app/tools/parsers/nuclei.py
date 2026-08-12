import json
import re

# Matches the version prefix of a CVSS vector string, e.g. "CVSS:3.1/AV:N/..."
# or "CVSS:4.0/AV:N/...". Verified against real nuclei JSON output (Phase 15
# audit): info.classification.cvss-metrics carries the vector with this
# prefix; the version is never a separate field on its own.
_CVSS_VECTOR_VERSION = re.compile(r"^CVSS:(\d+\.\d+)/")


def _cvss_version_from_vector(vector: str | None) -> str | None:
    if not vector:
        return None
    match = _CVSS_VECTOR_VERSION.match(vector)
    return match.group(1) if match else None


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
        classification = info.get("classification") or {}

        # Verified real shape (Phase 15 audit, live nuclei run): cve-id is a
        # list of lowercased strings when present, e.g. ["cve-2021-44228"].
        # Normalized to uppercase here -- EPSS/KEV/NVD all key on the
        # canonical "CVE-YYYY-NNNNN" form.
        raw_cve_ids = classification.get("cve-id") or []
        cve_ids = sorted({str(c).upper() for c in raw_cve_ids if c})

        cvss_vector = classification.get("cvss-metrics")
        cvss_score = classification.get("cvss-score")

        findings.append(
            {
                "template_id": record.get("template-id"),
                "name": info.get("name"),
                "severity": (info.get("severity") or "unknown").lower(),
                "matched_at": record.get("matched-at") or record.get("host"),
                "description": info.get("description"),
                "cve_ids": cve_ids,
                "cvss_score": float(cvss_score) if isinstance(cvss_score, (int, float)) else None,
                "cvss_vector": cvss_vector,
                "cvss_version": _cvss_version_from_vector(cvss_vector),
            }
        )
    return {"findings": findings}


def cvss_hints(parsed: dict) -> list[dict]:
    """CVE/CVSS pairs a nuclei run already told us, straight from the
    template's `classification` block -- no NVD call needed for these (see
    app/risk/service.py::seed_cvss_from_tool, wired into
    app/jobs/tasks.py::execute_job). Only entries with both a CVE and a
    score are returned; a template can carry a CVE with no CVSS in its
    metadata (rare but real), which is simply skipped here.
    """
    hints = []
    for item in parsed.get("findings", []):
        score = item.get("cvss_score")
        if score is None:
            continue
        for cve in item.get("cve_ids") or []:
            hints.append(
                {
                    "cve": cve,
                    "cvss_score": score,
                    "cvss_version": item.get("cvss_version"),
                    "cvss_vector": item.get("cvss_vector"),
                }
            )
    return hints
