import httpx
import pytest

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
