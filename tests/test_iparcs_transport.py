import json
from urllib.error import HTTPError

import pytest

from tennisrungs_mcp import iparcs_consumer as ip


def test_public_transport_has_no_credential_headers_and_uses_observed_query(monkeypatch):
    class Response:
        headers = type("Headers", (), {"get_content_type": lambda _: "application/json"})()
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self): return json.dumps({"headers": {"response_code": "0000"}, "body": {}}).encode()
    class Opener:
        def open(self, req, timeout):
            assert req.full_url.startswith(ip.BASE + "/rest/reservation/resource?")
            assert req.method == "POST"
            headers = {k.lower(): v for k, v in req.header_items()}
            assert "cookie" not in headers and "authorization" not in headers and "x-csrf-token" not in headers
            assert json.loads(req.data)["name"] == "synthetic"
            return Response()
    monkeypatch.setattr(ip, "build_opener", lambda *_: Opener())
    ip.PublicTransport().request("POST", "/rest/reservation/resource?locale=en-US", ip.search_body("synthetic"))


@pytest.mark.parametrize("status", [302, 403, 429])
def test_redirect_denial_rate_limit_are_single_attempt_and_sanitized(monkeypatch, status):
    calls = []
    class Opener:
        def open(self, req, timeout):
            calls.append(req)
            raise HTTPError(req.full_url, status, "private-detail-marker", {}, None)
    monkeypatch.setattr(ip, "build_opener", lambda *_: Opener())
    with pytest.raises(ip.BoundaryError) as e:
        ip.PublicTransport().request("GET", "/rest/reservation/resource/detail/1")
    assert len(calls) == 1 and "private-detail-marker" not in str(e.value)
