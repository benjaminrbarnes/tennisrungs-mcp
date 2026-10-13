import http.cookiejar
import json
import logging
from urllib.parse import urljoin, urlparse

import httpx

from .models import AuthenticationRequired, IntegrationError, UnknownOutcome
from .parsers import is_login

BASE = "https://app.tennisrungs.com"


class Transport:
    """Single-attempt requests; no TLS bypass, browser impersonation or challenge solver."""

    def __init__(self, cookies=None, client=None):
        # httpx INFO logs full URLs. The legacy proposal contract places hidden
        # form fields in the query string; host logging must not expose them.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        self.client = client or httpx.Client(timeout=20, follow_redirects=False,
                                            headers={"User-Agent": "tennisrungs-mcp/0.1.0"})
        if cookies:
            for c in cookies:
                # A credential bundle is site-bound. Reject broad/unrelated domains.
                if c["domain"] not in ("app.tennisrungs.com", ".tennisrungs.com", "tennisrungs.com"):
                    raise AuthenticationRequired("Credential bundle contains an unrelated domain")
                self.client.cookies.jar.set_cookie(http.cookiejar.Cookie(
                    0, c["name"], c["value"], None, False, c["domain"], True,
                    c["domain"].startswith("."), c.get("path", "/"), True,
                    True, c.get("expires"), c.get("expires") is None,
                    None, None, {"HttpOnly": None}, False))

    def close(self):
        self.client.close()

    def cookie_bundle(self):
        return [{"name": c.name, "value": c.value, "domain": c.domain,
                 "path": c.path, "expires": c.expires}
                for c in self.client.cookies.jar
                if c.domain in ("app.tennisrungs.com", ".tennisrungs.com", "tennisrungs.com")]

    def request(self, method, path, *, private=False, data=None, params=None):
        if not path.startswith("/") or path.startswith("//"):
            raise IntegrationError("Only same-site paths are supported")
        if private and not self.cookie_bundle():
            raise AuthenticationRequired("No approved session configured; use explicit local login after approval")
        url = BASE + path
        try:
            for _ in range(4):
                r = self.client.request(method, url, data=data, params=params)
                if 300 <= r.status_code < 400:
                    if method != "GET":
                        raise UnknownOutcome("Write redirected; inspect account state before any retry")
                    url = urljoin(url, r.headers.get("location", ""))
                    if urlparse(url).netloc != "app.tennisrungs.com" or urlparse(url).scheme != "https":
                        raise IntegrationError("Cross-site redirect refused")
                    if "/Account/" in url:
                        raise AuthenticationRequired("Session absent or expired; renewal required")
                    params = None
                    continue
                if r.status_code in (401, 403):
                    raise AuthenticationRequired(f"HTTP {r.status_code}; access denied, no workaround attempted")
                if r.status_code == 429:
                    raise IntegrationError("Rate limited; stop and respect Retry-After outside this request")
                if r.status_code >= 400:
                    if method == "POST":
                        raise UnknownOutcome("Write returned an error; reconcile before retry")
                    raise IntegrationError(f"HTTP {r.status_code}; response body suppressed")
                if is_login(r.text):
                    raise AuthenticationRequired("Login page received instead of account data")
                return r.text
            raise IntegrationError("Redirect limit reached")
        except httpx.RequestError:
            if method == "POST":
                raise UnknownOutcome("Write transport failed; outcome unknown, do not retry") from None
            raise IntegrationError("Read transport failed; details suppressed") from None

    def get(self, path, *, private=False):
        return self.request("GET", path, private=private)

    def post(self, path, *, data=None, params=None):
        return self.request("POST", path, private=True, data=data, params=params)


def parse_write_response(raw):
    try:
        j = json.loads(raw)
    except (ValueError, TypeError):
        raise UnknownOutcome("Unexpected write response; reconcile live state") from None
    if not isinstance(j, dict):
        raise UnknownOutcome("Unexpected write response shape")
    # Do not return or journal arbitrary site messages/HTML, which could contain private data.
    if j.get("Success") is True or j.get("ErrorsOccurred") is False:
        return True
    if j.get("Success") is False or j.get("ErrorsOccurred") is True:
        return False
    # PostJson proposal success historically uses Message rather than a structured flag.
    if j.get("Message") == "Proposal Successfully Posted!":
        return True
    raise UnknownOutcome("Unrecognized response semantics; reconcile live state")
