import httpx
import pytest

from tennisrungs_mcp.models import AuthenticationRequired, IntegrationError, UnknownOutcome
from tennisrungs_mcp.transport import Transport, parse_write_response

COOKIE = [{"name": "test_session", "value": "synthetic-only", "domain": "app.tennisrungs.com"}]


def transport(handler, cookies=None):
    return Transport(cookies, httpx.Client(transport=httpx.MockTransport(handler)))


def test_public_requires_no_session_and_private_requires_session():
    t = transport(lambda r: httpx.Response(200, text="public"))
    assert t.get("/Public/PlayerMatches?teamId=201") == "public"
    with pytest.raises(AuthenticationRequired):
        t.get("/Player", private=True)


def test_no_cross_site_redirect_or_cookie_transmission():
    seen = []
    def handler(r):
        seen.append(r.url.host)
        return httpx.Response(302, headers={"location": "https://example.com/"})
    with pytest.raises(IntegrationError):
        transport(handler, COOKIE).get("/Player", private=True)
    assert seen == ["app.tennisrungs.com"]


@pytest.mark.parametrize("status", [401, 403, 429])
def test_denial_and_rate_limit_are_not_retried(status):
    seen = []
    def handler(r):
        seen.append(r)
        return httpx.Response(status, text="sensitive-details-suppressed")
    with pytest.raises(IntegrationError) as e:
        transport(handler).get("/Public/PlayerMatches?teamId=201")
    assert "sensitive" not in str(e.value)
    assert len(seen) == 1


def test_timeout_on_post_is_unknown_and_single_attempt():
    seen = []
    def handler(r):
        seen.append(r)
        raise httpx.ReadTimeout("secret request context", request=r)
    with pytest.raises(UnknownOutcome) as e:
        transport(handler, COOKIE).post("/Player/WithdrawChallenge", data={"challengeId": 303})
    assert len(seen) == 1 and "secret" not in str(e.value)


def test_login_html_is_not_account_success():
    with pytest.raises(AuthenticationRequired):
        transport(lambda r: httpx.Response(200, text='<input type="password">')).get("/Player")


def test_response_semantics_not_http_success():
    assert not parse_write_response('{"Success":false}')
    with pytest.raises(UnknownOutcome):
        parse_write_response('{"Message":"some unknown outcome"}')


def test_unrelated_credential_domains_refused():
    with pytest.raises(AuthenticationRequired):
        transport(lambda r: httpx.Response(200), [{"name": "x", "value": "synthetic", "domain": "example.com"}])
