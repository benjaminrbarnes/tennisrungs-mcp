"""Synthetic credentials/responses only; never calls the live account."""
import json
from email.message import Message
from urllib.error import URLError
from urllib.request import Request

import pytest

from tennisrungs_mcp import cli
from tennisrungs_mcp.iparcs_consumer import BoundaryError
from tennisrungs_mcp.iparcs_login import (NormalLogin, SIGNIN_POST, LOGINCHECK, LOGINUSER,
                                         login_and_optionally_store)
from tennisrungs_mcp.iparcs_login_bootstrap import (AnonymousLoginSession, ExactSignInRedirect,
                                                  FINAL_SIGNIN, SIGNIN, parse_bootstrap)
from test_iparcs_login_bootstrap import html, jar, response


class Reply:
    def __init__(self, payload, *, status=202, extra_headers=None):
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        for k, v in (extra_headers or {}).items(): self.headers[k] = v
        self.payload = json.dumps(payload).encode()
    def read(self, n): return self.payload[:n]
    def __enter__(self): return self
    def __exit__(self, *args): pass


def envelope(body, code="0000"):
    return dict(headers={"response_code": code}, body=body)


def session(responses=None, *, enabled=True, failed=1):
    class Opener:
        def __init__(self): self.seen = []; self.responses = list(responses or [])
        def open(self, req, timeout):
            self.seen.append(req)
            out = self.responses.pop(0)
            if isinstance(out, Exception): raise out
            return out
    return AnonymousLoginSession(parse_bootstrap(html(enabled=enabled, failed=failed), FINAL_SIGNIN), jar(), Opener())


def success_reads():
    return [Reply(response()), Reply(envelope({})),
            Reply(envelope({"user": {"customerid": 42, "loginname": "synthetic-user", "email": "synthetic@example.invalid"}}))]


def test_single_same_context_post_then_two_reads_preserves_cookie_flags_no_password_bundle():
    s = session(success_reads())
    flow = NormalLogin(s)
    verified = flow.login("synthetic-user", "synthetic-password-marker", approval_reference="synthetic")
    seen = s._opener.seen
    assert [(r.method, r.full_url) for r in seen] == [("POST", SIGNIN_POST), ("GET", LOGINCHECK), ("GET", LOGINUSER)]
    assert seen[0].get_header("X-csrf-token") == s.context.csrf
    assert "force_logged_off" not in json.loads(seen[0].data)
    assert verified.diagnostics()["account_identity_matched"]
    assert "synthetic-password-marker" not in repr(verified._bundle)
    assert "synthetic-cookie-marker" not in repr(verified)
    assert "synthetic" not in repr(verified.diagnostics())
    for cookie in verified._bundle["cookies"]:
        assert cookie["secure"] and "HttpOnly" in cookie["rest"]
        assert cookie["expires"] is None and cookie["discard"]
    with pytest.raises(BoundaryError, match="One login attempt"):
        flow.login("synthetic-user", "synthetic-password-marker", approval_reference="synthetic")
    assert len(seen) == 3


@pytest.mark.parametrize("bad", [response(success=False, error_type=12), response(need_verify_recaptcha=True),
                               response(security_sign_token="synthetic-token"), response(redirect_url="https://example.invalid"),
                               response(unknown_security_field=True)])
def test_stop_after_one_post_no_readback_or_storage(bad):
    s = session([Reply(bad)])
    stored = []
    with pytest.raises(BoundaryError):
        login_and_optionally_store("synthetic-user", "synthetic-password", approval_reference="synthetic",
                                  approve_storage=True, session=s, store=stored.append)
    assert len(s._opener.seen) == 1 and not stored


@pytest.mark.parametrize("baduser", [{}, {"customerid": True, "loginname": "synthetic-user"},
                                  {"customerid": -1, "loginname": "synthetic-user"},
                                  {"customerid": 42, "loginname": "someone-else"}])
def test_verified_readback_identity_required_before_storage(baduser):
    s = session([Reply(response()), Reply(envelope({})), Reply(envelope({"user": baduser}))])
    stored = []
    with pytest.raises(BoundaryError):
        login_and_optionally_store("synthetic-user", "synthetic-password", approval_reference="synthetic",
                                  approve_storage=True, session=s, store=stored.append)
    assert not stored


def test_anonymous_logincheck_even_with_cookie_names_refuses_storage():
    s = session([Reply(response()), Reply(envelope({}, "0021"))])
    with pytest.raises(BoundaryError, match="readback"):
        NormalLogin(s).login("synthetic-user", "synthetic-password", approval_reference="synthetic")
    assert len(s._opener.seen) == 2


def test_storage_only_when_explicit_and_after_all_reads():
    for approved in [False, True]:
        s = session(success_reads()); stored = []
        def store(bundle):
            assert len(s._opener.seen) == 3
            stored.append(bundle)
        r = login_and_optionally_store("synthetic-user", "synthetic-password", approval_reference="synthetic",
                                      approve_storage=approved, session=s, store=store)
        assert r["session_stored"] == approved and bool(stored) == approved
        assert "synthetic" not in repr(r)


def test_transport_failure_has_no_retry_or_secret_error():
    s = session([URLError("synthetic-password-marker")]); flow = NormalLogin(s)
    with pytest.raises(BoundaryError) as exc:
        flow.login("synthetic-user", "synthetic-password-marker", approval_reference="synthetic")
    assert "synthetic" not in str(exc.value)
    with pytest.raises(BoundaryError): flow.login("x", "y", approval_reference="synthetic")
    assert len(s._opener.seen) == 1


def test_rotated_csrf_stops_before_persistence():
    s = session([Reply(response(), extra_headers={"X-CSRF-Token": "synthetic-rotated-token"})])
    with pytest.raises(BoundaryError, match="rotation"):
        NormalLogin(s).login("synthetic-user", "synthetic-password", approval_reference="synthetic")


def test_redirect_handler_allows_only_original_get_locale_redirect():
    h = ExactSignInRedirect()
    assert h.redirect_request(Request(SIGNIN), None, 302, "", {}, FINAL_SIGNIN).full_url == FINAL_SIGNIN
    for method, url, target in [("POST", SIGNIN_POST, FINAL_SIGNIN), ("GET", LOGINCHECK, FINAL_SIGNIN),
                                ("GET", SIGNIN, "https://example.invalid")]:
        with pytest.raises(BoundaryError): h.redirect_request(Request(url, method=method), None, 302, "", {}, target)


def test_dispatch_allowlist_refuses_cart_and_unknown_cookie_before_send():
    s = session([])
    with pytest.raises(BoundaryError): NormalLogin(s)._json("POST", SIGNIN_POST.replace("/user/signin", "/checkout"), body={})
    s._jar = jar([("other_JSESSIONID", ".apm.activecommunities.com")])
    with pytest.raises(BoundaryError): NormalLogin(s)._json("GET", LOGINUSER)
    assert not s._opener.seen


def test_cli_requires_transmission_approval_before_bootstrap(monkeypatch):
    from tennisrungs_mcp import iparcs_login_bootstrap
    monkeypatch.setattr(iparcs_login_bootstrap, "acquire_anonymous_bootstrap", lambda: pytest.fail("no approval"))
    with pytest.raises(SystemExit): cli.main(["iparcs", "login"])


def test_cli_captcha_stops_before_prompt_or_keychain(monkeypatch, capsys):
    from tennisrungs_mcp import iparcs_login_bootstrap
    monkeypatch.setattr(iparcs_login_bootstrap, "acquire_anonymous_bootstrap", lambda: session(failed=0))
    monkeypatch.setattr(cli, "prompt_credentials", lambda _: pytest.fail("CAPTCHA must stop before secrets"))
    monkeypatch.setattr(cli, "Keychain", lambda **_: pytest.fail("CAPTCHA must stop before storage"))
    assert cli.main(["iparcs", "login", "--approve-credential-transmission", "--approve-session-storage"]) == 2
    assert "CAPTCHA" in capsys.readouterr().err


def test_cli_in_memory_login_no_keychain_or_secret_output(monkeypatch, capsys):
    from tennisrungs_mcp import iparcs_login_bootstrap
    s = session(success_reads())
    monkeypatch.setattr(iparcs_login_bootstrap, "acquire_anonymous_bootstrap", lambda: s)
    monkeypatch.setattr(cli, "prompt_credentials", lambda _: ("synthetic-user", "synthetic-password-marker"))
    monkeypatch.setattr(cli, "Keychain", lambda **_: pytest.fail("storage not approved"))
    assert cli.main(["iparcs", "login", "--approve-credential-transmission"]) == 0
    out = capsys.readouterr()
    assert "synthetic" not in out.out + out.err
    assert json.loads(out.out)["session_stored"] is False
