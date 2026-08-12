import httpx
import pytest

from app.intel.nvd import NVDFetchError, fetch_nvd_cvss


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_nvd_cvss_prefers_v31_over_v2():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "vulnerabilities": [
                    {
                        "cve": {
                            "id": "CVE-2021-44228",
                            "metrics": {
                                "cvssMetricV31": [
                                    {"cvssData": {"version": "3.1", "baseScore": 10.0, "vectorString": "CVSS:3.1/AV:N"}}
                                ],
                                "cvssMetricV2": [{"cvssData": {"version": "2.0", "baseScore": 9.3}}],
                            },
                        }
                    }
                ]
            },
        )

    result = fetch_nvd_cvss("CVE-2021-44228", client=_client(handler))
    assert result == {"score": 10.0, "version": "3.1", "vector": "CVSS:3.1/AV:N"}


def test_fetch_nvd_cvss_falls_back_to_v2_when_no_v3():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "vulnerabilities": [
                    {"cve": {"metrics": {"cvssMetricV2": [{"cvssData": {"version": "2.0", "baseScore": 7.5}}]}}}
                ]
            },
        )

    result = fetch_nvd_cvss("CVE-2010-0001", client=_client(handler))
    assert result["version"] == "2.0"
    assert result["score"] == 7.5


def test_fetch_nvd_cvss_cve_not_found_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"vulnerabilities": []})

    result = fetch_nvd_cvss("CVE-9999-99999", client=_client(handler))
    assert result is None


def test_fetch_nvd_cvss_no_metrics_at_all_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"vulnerabilities": [{"cve": {"metrics": {}}}]})

    result = fetch_nvd_cvss("CVE-2024-00001", client=_client(handler))
    assert result is None


def test_fetch_nvd_cvss_timeout_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    with pytest.raises(NVDFetchError):
        fetch_nvd_cvss("CVE-2021-44228", client=_client(handler))


def test_fetch_nvd_cvss_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(NVDFetchError):
        fetch_nvd_cvss("CVE-2021-44228", client=_client(handler))


def test_fetch_nvd_cvss_malformed_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    with pytest.raises(NVDFetchError):
        fetch_nvd_cvss("CVE-2021-44228", client=_client(handler))
