"""FIRST.org EPSS API client. Verified against the real API (Phase 15 audit,
2026-08-12): `GET https://api.first.org/data/v1/epss?cve=CVE-A,CVE-B` ->
`{"status":"OK","data":[{"cve":"CVE-...","epss":"0.999990000","percentile":"1.000000000","date":"..."}]}`.
No API key required.

Deliberately queried per-CVE-batch (the CVEs CyberLab has actually seen),
never the full daily EPSS catalog (hundreds of thousands of rows) -- see
docs/phase-15-risk-score.md for why.
"""

import httpx

EPSS_API_URL = "https://api.first.org/data/v1/epss"

# FIRST.org accepts a comma-separated CVE list; kept well under any URL
# length limit and any reasonable per-request payload size.
BATCH_SIZE = 100


class EPSSFetchError(Exception):
    pass


def fetch_epss_scores(cve_ids: list[str], *, client: httpx.Client | None = None, timeout: float = 15.0) -> dict[str, dict]:
    """Returns {CVE: {"epss": float, "percentile": float}} for whichever of
    `cve_ids` FIRST.org has data for. A CVE absent from the response simply
    has no EPSS score yet (not an error) and is absent from the result.
    """
    if not cve_ids:
        return {}

    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    results: dict[str, dict] = {}
    try:
        for i in range(0, len(cve_ids), BATCH_SIZE):
            batch = cve_ids[i : i + BATCH_SIZE]
            try:
                response = client.get(EPSS_API_URL, params={"cve": ",".join(batch)})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise EPSSFetchError(f"EPSS request failed: {exc}") from exc

            try:
                payload = response.json()
            except ValueError as exc:
                raise EPSSFetchError(f"EPSS returned malformed JSON: {exc}") from exc

            for entry in payload.get("data", []) or []:
                cve = entry.get("cve")
                if not cve:
                    continue
                try:
                    results[str(cve).upper()] = {
                        "epss": float(entry["epss"]),
                        "percentile": float(entry["percentile"]),
                    }
                except (KeyError, TypeError, ValueError):
                    # One malformed entry must not fail the whole batch.
                    continue
    finally:
        if owns_client:
            client.close()
    return results
