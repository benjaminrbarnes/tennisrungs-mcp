"""Bounded, same-site reads. The separate login helper owns the sole login POST."""
import http.cookiejar
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

from .models import AuthenticationRequired, IntegrationError
from .parsers import is_login

BASE = "https://app.tennisrungs.com"


def validate_cookies(cookies):
    if not isinstance(cookies, list) or not cookies or len(cookies) > 64:
        raise AuthenticationRequired("Site session missing or invalid")
    for cookie in cookies:
        if (not isinstance(cookie, dict)
                or set(cookie) - {"name", "value", "domain", "path", "expires"}
                or not {"name", "value", "domain"}.issubset(cookie)):
            raise AuthenticationRequired("Site cookie schema invalid; values suppressed")
        if not isinstance(cookie["domain"], str) or cookie["domain"] not in {"app.tennisrungs.com", ".tennisrungs.com", "tennisrungs.com"}:
            raise AuthenticationRequired("Session cookie target outside fixed site")
        if (not all(isinstance(cookie[k], str) and cookie[k] and len(cookie[k]) <= 16384
                    for k in ["name", "value"])
                or not isinstance(cookie.get("path", "/"), str)
                or not cookie.get("path", "/").startswith("/")
                or cookie.get("expires") is not None and type(cookie["expires"]) is not int):
            raise AuthenticationRequired("Site cookie invalid; values suppressed")
    return cookies


def read_path(path):
    return isinstance(path, str) and (path == "/Player"
        or re.fullmatch(r"/Ladders/Rankings/[1-9][0-9]*", path)
        or re.fullmatch(r"/Public/PlayerMatches\?teamId=[1-9][0-9]*", path))


class Transport:
    """No arbitrary endpoints, mutation calls, automatic retries or TLS bypass."""
    def __init__(self, cookies=None, client=None):
        if cookies is not None:
            validate_cookies(cookies)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        self.client = client or httpx.Client(timeout=20, follow_redirects=False,
                                            headers={"User-Agent": "tennisrungs-mcp/0.2.0"})
        for cookie in cookies or []:
            self.client.cookies.jar.set_cookie(http.cookiejar.Cookie(
                0, cookie["name"], cookie["value"], None, False, cookie["domain"], True,
                cookie["domain"].startswith("."), cookie.get("path", "/"), True,
                True, cookie.get("expires"), cookie.get("expires") is None,
                None, None, {"HttpOnly": None}, False))

    def close(self):
        self.client.close()

    def cookie_bundle(self):
        return [{"name": c.name, "value": c.value, "domain": c.domain,
                 "path": c.path, "expires": c.expires}
                for c in self.client.cookies.jar
                if c.domain in ("app.tennisrungs.com", ".tennisrungs.com", "tennisrungs.com")]

    def request(self, method, path, *, private=False, data=None, params=None):
        if method != "GET" or data is not None or params is not None or not read_path(path):
            raise IntegrationError("Only allowlisted TennisRungs reads are supported")
        if private and not self.cookie_bundle():
            raise AuthenticationRequired("No session configured; run the local login command")
        url = BASE + path
        try:
            for _ in range(4):
                response = self.client.get(url)
                if 300 <= response.status_code < 400:
                    target = urljoin(url, response.headers.get("location", ""))
                    parsed = urlparse(target)
                    if parsed.netloc != "app.tennisrungs.com" or parsed.scheme != "https":
                        raise IntegrationError("Cross-site redirect refused")
                    if parsed.path.startswith("/Account/"):
                        raise AuthenticationRequired("Session absent or expired; renewal required")
                    target_path = parsed.path + ("?" + parsed.query if parsed.query else "")
                    if not read_path(target_path) or parsed.fragment:
                        raise IntegrationError("Redirect outside supported read routes")
                    url = target
                    continue
                if response.status_code in (401, 403):
                    raise AuthenticationRequired(f"HTTP {response.status_code}; access denied")
                if response.status_code == 429:
                    raise IntegrationError("Rate limited; stop and respect Retry-After")
                if response.status_code >= 400:
                    raise IntegrationError(f"HTTP {response.status_code}; response body suppressed")
                if is_login(response.text):
                    raise AuthenticationRequired("Login page received instead of account data")
                return response.text
            raise IntegrationError("Redirect limit reached")
        except httpx.RequestError:
            raise IntegrationError("Read transport failed; details suppressed") from None

    def get(self, path, *, private=False):
        return self.request("GET", path, private=private)
