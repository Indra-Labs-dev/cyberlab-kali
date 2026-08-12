import httpx
import pytest

from app.intel.cisa_kev import CisaKevFetchError, fetch_cisa_kev_catalog


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_cisa_kev_catalog_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "catalogVersion": "2026.08.12",
                "count": 1,
                "vulnerabilities": [
                    {
                        "cveID": "CVE-2021-44228",
                        "vendorProject": "Apache",
                        "product": "Log4j",
                        "vulnerabilityName": "Apache Log4j RCE",
                        "dateAdded": "2021-12-10",
                        "dueDate": "2021-12-24",
                        "knownRansomwareCampaignUse": "Known",
                    }
                ],
            },
        )

    entries = fetch_cisa_kev_catalog(client=_client(handler))
    assert len(entries) == 1
    assert entries[0]["cve_id"] == "CVE-2021-44228"
    assert entries[0]["known_ransomware_campaign_use"] is True
    assert entries[0]["date_added"].isoformat() == "2021-12-10"


def test_fetch_cisa_kev_catalog_unknown_ransomware_use_is_false():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"vulnerabilities": [{"cveID": "CVE-2020-1", "knownRansomwareCampaignUse": "Unknown"}]},
        )

    entries = fetch_cisa_kev_catalog(client=_client(handler))
    assert entries[0]["known_ransomware_campaign_use"] is False


def test_fetch_cisa_kev_catalog_entry_missing_cve_id_is_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"vulnerabilities": [{"vendorProject": "NoID"}, {"cveID": "CVE-2020-2"}]})

    entries = fetch_cisa_kev_catalog(client=_client(handler))
    assert len(entries) == 1
    assert entries[0]["cve_id"] == "CVE-2020-2"


def test_fetch_cisa_kev_catalog_malformed_date_is_none_not_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"vulnerabilities": [{"cveID": "CVE-2020-3", "dateAdded": "not-a-date"}]})

    entries = fetch_cisa_kev_catalog(client=_client(handler))
    assert entries[0]["date_added"] is None


def test_fetch_cisa_kev_catalog_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(CisaKevFetchError):
        fetch_cisa_kev_catalog(client=_client(handler))


def test_fetch_cisa_kev_catalog_malformed_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not json")

    with pytest.raises(CisaKevFetchError):
        fetch_cisa_kev_catalog(client=_client(handler))


def test_fetch_cisa_kev_catalog_missing_vulnerabilities_key_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"catalogVersion": "x"})

    with pytest.raises(CisaKevFetchError):
        fetch_cisa_kev_catalog(client=_client(handler))
