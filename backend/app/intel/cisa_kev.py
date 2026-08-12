"""CISA Known Exploited Vulnerabilities catalog client. Verified against the
real feed (Phase 15 audit, 2026-08-12): a single JSON file, ~1,665 entries,
~1.5MB -- `{"catalogVersion": "...", "count": N, "vulnerabilities": [...]}`,
each entry carrying `cveID`/`dateAdded`/`dueDate`/`knownRansomwareCampaignUse`
(the string `"Known"` or `"Unknown"`, not a boolean).

Fetched wholesale (unlike EPSS): CISA publishes no per-CVE query API, and
the catalog is small and bounded -- a justified full download, not an NVD
-scale dump. See docs/phase-15-risk-score.md.
"""

from datetime import date

import httpx

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


class CisaKevFetchError(Exception):
    pass


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def fetch_cisa_kev_catalog(*, client: httpx.Client | None = None, timeout: float = 30.0) -> list[dict]:
    """Returns the full catalog as a list of plain dicts (cve_id/
    vendor_project/product/vulnerability_name/date_added/due_date/
    known_ransomware_campaign_use). Raises CisaKevFetchError on any
    network/HTTP/parsing failure -- callers must not treat a failed fetch as
    "empty catalog".
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        try:
            response = client.get(CISA_KEV_URL)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CisaKevFetchError(f"CISA KEV request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise CisaKevFetchError(f"CISA KEV returned malformed JSON: {exc}") from exc

        vulnerabilities = payload.get("vulnerabilities")
        if not isinstance(vulnerabilities, list):
            raise CisaKevFetchError("CISA KEV response missing a 'vulnerabilities' list")

        entries = []
        for item in vulnerabilities:
            cve_id = item.get("cveID")
            if not cve_id:
                continue
            entries.append(
                {
                    "cve_id": str(cve_id).upper(),
                    "vendor_project": item.get("vendorProject"),
                    "product": item.get("product"),
                    "vulnerability_name": item.get("vulnerabilityName"),
                    "date_added": _parse_date(item.get("dateAdded")),
                    "due_date": _parse_date(item.get("dueDate")),
                    "known_ransomware_campaign_use": item.get("knownRansomwareCampaignUse") == "Known",
                }
            )
        return entries
    finally:
        if owns_client:
            client.close()
