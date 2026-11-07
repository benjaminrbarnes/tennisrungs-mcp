import httpx
import pytest
import warnings
import getpass

from tennisrungs_mcp import auth
from tennisrungs_mcp.models import AuthenticationRequired, UnsupportedContract
from tennisrungs_mcp.transport import Transport
from fixtures import dashboard

LOGIN = '<form method="post" action="/Account/Login"><input name="UserName"><input type="password" name="Password"><input type="checkbox" name="remember"></form>'


def install_transport(monkeypatch, handler):
    monkeypatch.setattr(auth, "Transport", lambda: Transport(client=httpx.Client(transport=httpx.MockTransport(handler))))


def test_normal_login_verifies_dashboard_and_returns_cookie_not_password(monkeypatch):
    seen = []
    def handler(r):
        seen.append(r)
        if r.method == "POST":
            assert r.url.path == "/Account/Login"
            return httpx.Response(302, headers={"location": "/Player", "set-cookie": "test_session=synthetic-session; Path=/; Secure; HttpOnly"})
        return httpx.Response(200, text=dashboard() if r.url.path == "/Player" else LOGIN)
    install_transport(monkeypatch, handler)
    cookies = auth.interactive_login("synthetic-user", "synthetic-password")
    assert cookies[0]["name"] == "test_session"
    assert "synthetic-password" not in str(cookies)
    assert [r.method for r in seen] == ["GET", "POST", "GET"]


def test_login_denial_stops_without_post(monkeypatch):
    seen = []
    def handler(r):
        seen.append(r)
        return httpx.Response(403)
    install_transport(monkeypatch, handler)
    with pytest.raises(AuthenticationRequired):
        auth.interactive_login("synthetic-user", "synthetic-password")
    assert len(seen) == 1


def test_unexpected_login_destination_never_receives_password(monkeypatch):
    seen = []
    def handler(r):
        seen.append(r)
        return httpx.Response(200, text=LOGIN.replace('/Account/Login', 'https://example.com/login'))
    install_transport(monkeypatch, handler)
    with pytest.raises(UnsupportedContract):
        auth.interactive_login("synthetic-user", "synthetic-password")
    assert len(seen) == 1


def test_rejected_password_is_not_retried(monkeypatch):
    seen = []
    def handler(r):
        seen.append(r)
        return httpx.Response(200, text=LOGIN)
    install_transport(monkeypatch, handler)
    with pytest.raises(AuthenticationRequired):
        auth.interactive_login("synthetic-user", "synthetic-password")
    assert [r.method for r in seen] == ["GET", "POST"]


def test_prompt_refuses_redirected_input_before_reading(monkeypatch):
    from tennisrungs_mcp.cli import prompt_credentials
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("must not read redirected credentials"))
    with pytest.raises(AuthenticationRequired, match="Terminal"):
        prompt_credentials()


def test_prompt_never_uses_echo_fallback(monkeypatch):
    from tennisrungs_mcp.cli import prompt_credentials
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "synthetic-user")
    def unavailable(_):
        warnings.warn("no secure terminal", getpass.GetPassWarning)
        pytest.fail("would have entered insecure fallback")
    monkeypatch.setattr(getpass, "getpass", unavailable)
    with pytest.raises(AuthenticationRequired, match="non-echo"):
        prompt_credentials()


def test_local_prompt_does_not_echo_password(capsys, monkeypatch):
    from tennisrungs_mcp.cli import prompt_credentials
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "synthetic-user")
    monkeypatch.setattr(getpass, "getpass", lambda _: "synthetic-password-marker")
    assert prompt_credentials() == ("synthetic-user", "synthetic-password-marker")
    assert "synthetic-password-marker" not in capsys.readouterr().out


def test_security_challenge_stops_before_password_post(monkeypatch):
    seen = []
    def handler(request):
        seen.append(request.method)
        return httpx.Response(200, text=LOGIN + '<div data-sitekey="synthetic-key"></div>')
    install_transport(monkeypatch, handler)
    with pytest.raises(AuthenticationRequired, match="security challenge"):
        auth.interactive_login("synthetic-user", "synthetic-password")
    assert seen == ["GET"]
