import httpx
import pytest

from app.intel.epss import EPSSFetchError, fetch_epss_scores


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_epss_scores_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "data": [
                    {"cve": "CVE-2021-44228", "epss": "0.99999", "percentile": "1.00000", "date": "2026-08-12"},
                    {"cve": "CVE-2016-10033", "epss": "0.99714", "percentile": "0.99951", "date": "2026-08-12"},
                ],
            },
        )

    result = fetch_epss_scores(["CVE-2021-44228", "CVE-2016-10033"], client=_client(handler))
    assert result["CVE-2021-44228"]["epss"] == pytest.approx(0.99999)
    assert result["CVE-2016-10033"]["percentile"] == pytest.approx(0.99951)


def test_fetch_epss_scores_empty_input_makes_no_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"data": []})

    result = fetch_epss_scores([], client=_client(handler))
    assert result == {}
    assert calls == []


def test_fetch_epss_scores_cve_not_in_response_is_absent_not_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "OK", "data": []})

    result = fetch_epss_scores(["CVE-9999-99999"], client=_client(handler))
    assert result == {}


def test_fetch_epss_scores_timeout_raises_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    with pytest.raises(EPSSFetchError):
        fetch_epss_scores(["CVE-2021-44228"], client=_client(handler))


def test_fetch_epss_scores_http_500_raises_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    with pytest.raises(EPSSFetchError):
        fetch_epss_scores(["CVE-2021-44228"], client=_client(handler))


def test_fetch_epss_scores_malformed_json_raises_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json{{{")

    with pytest.raises(EPSSFetchError):
        fetch_epss_scores(["CVE-2021-44228"], client=_client(handler))


def test_fetch_epss_scores_one_malformed_entry_does_not_fail_whole_batch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "data": [
                    {"cve": "CVE-2021-44228", "epss": "not-a-number", "percentile": "1.0"},
                    {"cve": "CVE-2016-10033", "epss": "0.5", "percentile": "0.9"},
                ],
            },
        )

    result = fetch_epss_scores(["CVE-2021-44228", "CVE-2016-10033"], client=_client(handler))
    assert "CVE-2021-44228" not in result
    assert result["CVE-2016-10033"]["epss"] == 0.5


def test_fetch_epss_scores_batches_large_cve_lists():
    seen_batches = []

    def handler(request: httpx.Request) -> httpx.Response:
        cve_param = request.url.params.get("cve")
        seen_batches.append(cve_param.split(","))
        return httpx.Response(200, json={"status": "OK", "data": []})

    cves = [f"CVE-2020-{i:05d}" for i in range(250)]
    fetch_epss_scores(cves, client=_client(handler))
    assert len(seen_batches) == 3  # 250 / 100 batch size -> 3 requests
    assert len(seen_batches[0]) == 100
    assert len(seen_batches[2]) == 50
