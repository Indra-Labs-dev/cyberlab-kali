"""NVD CVE API 2.0 client -- used only to enrich a CVE that has no CVSS from
any tool output. Verified against the real API (Phase 15 audit,
2026-08-12): `GET https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-...`
-> `vulnerabilities[0].cve.metrics.{cvssMetricV40,cvssMetricV31,cvssMetricV30,cvssMetricV2}[0].cvssData.{baseScore,version,vectorString}`.
Not every CVE carries every metric version -- highest available is
preferred, and the version actually used is always recorded (never
conflating a v2 score with a v3.1 one).

No API key required, but NVD rate-limits unauthenticated callers to ~5
requests per rolling 30s window -- app/intel/sync.py sleeps between calls,
this module makes exactly one request per call and never retries in a tight
loop.
"""

import httpx

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

# Preference order when a CVE has multiple CVSS versions -- newest first,
# matching the spec's requirement to never silently conflate versions.
_CVSS_METRIC_KEYS = ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2")


class NVDFetchError(Exception):
    pass


def fetch_nvd_cvss(cve: str, *, client: httpx.Client | None = None, timeout: float = 15.0) -> dict | None:
    """Returns {"score": float, "version": str, "vector": str | None} for the
    highest-priority CVSS version NVD has, or None if NVD has no CVSS data
    for this CVE at all (a real, valid outcome -- not every CVE is scored).
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        try:
            response = client.get(NVD_API_URL, params={"cveId": cve})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NVDFetchError(f"NVD request failed for {cve}: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise NVDFetchError(f"NVD returned malformed JSON for {cve}: {exc}") from exc

        vulnerabilities = payload.get("vulnerabilities") or []
        if not vulnerabilities:
            return None

        cve_data = (vulnerabilities[0] or {}).get("cve") or {}
        metrics = cve_data.get("metrics") or {}
        for key in _CVSS_METRIC_KEYS:
            entries = metrics.get(key)
            if not entries:
                continue
            cvss_data = (entries[0] or {}).get("cvssData") or {}
            score = cvss_data.get("baseScore")
            version = cvss_data.get("version")
            if score is None or not version:
                continue
            return {
                "score": float(score),
                "version": str(version),
                "vector": cvss_data.get("vectorString"),
            }
        return None
    finally:
        if owns_client:
            client.close()
