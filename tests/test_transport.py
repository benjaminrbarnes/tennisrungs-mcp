import logging
import httpx
import pytest
from tennisrungs_mcp.models import AuthenticationRequired, IntegrationError
from tennisrungs_mcp.transport import Transport

COOKIE = [{"name": "test_session", "value": "synthetic-only", "domain": "app.tennisrungs.com"}]


def transport(handler, cookies=None):
    return Transport(cookies, httpx.Client(transport=httpx.MockTransport(handler)))


def test_public_and_authenticated_read_boundaries():
    t = transport(lambda r: httpx.Response(200, text="public"))
    assert t.get("/Public/PlayerMatches?teamId=201") == "public"
    with pytest.raises(AuthenticationRequired): t.get("/Player", private=True)


def test_cross_site_redirect_does_not_transmit_cookies():
    seen = []
    def handler(r):
        seen.append(r.url.host)
        return httpx.Response(302, headers={"location": "https://example.com/"})
    with pytest.raises(IntegrationError): transport(handler, COOKIE).get("/Player", private=True)
    assert seen == ["app.tennisrungs.com"]


@pytest.mark.parametrize("method,path", [
    ("POST", "/Player/WithdrawChallenge"), ("PUT", "/Player"),
    ("GET", "/Account/LogOff"), ("GET", "//example.com/Player"),
    ("GET", "/Public/PlayerMatches?teamId=1&extra=2"),
])
def test_unlisted_or_mutating_requests_stop_before_network(method, path):
    def denied(r): pytest.fail("must not make a request")
    with pytest.raises(IntegrationError): transport(denied, COOKIE).request(method, path)


def test_read_redirect_cannot_follow_a_mutating_get_endpoint():
    seen = []
    def handler(r):
        seen.append(r)
        return httpx.Response(302, headers={"location": "/Account/LogOff"})
    with pytest.raises(IntegrationError): transport(handler, COOKIE).get("/Player", private=True)
    assert len(seen) == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_denial_is_single_attempt_with_sanitized_errors(status):
    calls = []
    def handler(r):
        calls.append(r)
        return httpx.Response(status, text="synthetic-sensitive-details")
    with pytest.raises(IntegrationError) as exc:
        transport(handler).get("/Public/PlayerMatches?teamId=201")
    assert "sensitive" not in str(exc.value) and len(calls) == 1


def test_read_timeout_does_not_retry_or_expose_request_context():
    calls = []
    def handler(r):
        calls.append(r)
        raise httpx.ReadTimeout("synthetic-private-context", request=r)
    with pytest.raises(IntegrationError) as exc:
        transport(handler).get("/Public/PlayerMatches?teamId=201")
    assert len(calls) == 1 and "private" not in str(exc.value)


def test_login_form_is_not_successful_account_data():
    with pytest.raises(AuthenticationRequired):
        transport(lambda r: httpx.Response(200, text='<input type="password">')).get("/Player")


@pytest.mark.parametrize("cookies", [
    [{"name": "x", "value": "synthetic", "domain": "example.com"}],
    [{"name": "x", "value": "synthetic", "domain": "app.tennisrungs.com", "expires": True}],
    [{"name": "x", "domain": "app.tennisrungs.com"}],
])
def test_unrelated_or_malformed_cookie_bundle_is_refused(cookies):
    with pytest.raises(AuthenticationRequired): transport(lambda r: httpx.Response(200), cookies)


def test_http_logs_do_not_expose_session_cookie(caplog):
    caplog.set_level(logging.DEBUG)
    transport(lambda r: httpx.Response(200, text="public"), COOKIE).get("/Player", private=True)
    assert "synthetic-only" not in caplog.text
