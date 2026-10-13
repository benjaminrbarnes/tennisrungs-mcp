"""Single new normal login, two authenticated reads and explicit Keychain opt-in.

Offline-tested protected flow. No browser export, retry, logout, account mutation,
waiver acceptance, preparation, cart or payment endpoints are available here.
"""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request

from .iparcs_consumer import BASE, BoundaryError
from .iparcs_login_bootstrap import (AnonymousLoginSession, acquire_anonymous_bootstrap,
                                     build_bootstrapped_login_request, classify_login_response,
                                     cookie_scope)

SERVICE = "tennis-iparcs"
ACCOUNT = "atlantadprca-consumer-session"
SIGNIN_POST = BASE + "/rest/user/signin?locale=en-US"
LOGINCHECK = BASE + "/rest/common/logincheck?locale=en-US"
LOGINUSER = BASE + "/rest/system/loginuser?locale=en-US"


@dataclass
class VerifiedSession:
    _bundle: dict = field(repr=False)

    def diagnostics(self):
        return {"authenticated_session_verified": True, "account_identity_matched": True,
                "readback_operations": ["logincheck", "loginuser"],
                "tenant": "atlantadprca", "cookie_count": len(self._bundle["cookies"]),
                "credential_values_exposed": False}


class NormalLogin:
    def __init__(self, session: AnonymousLoginSession):
        self.session = session
        self.attempted = False

    def _json(self, method, url, *, headers=None, body=None):
        allowed = (method == "POST" and url == SIGNIN_POST and body is not None) or (method == "GET" and url in [LOGINCHECK, LOGINUSER] and body is None)
        if not allowed:
            raise BoundaryError("Login flow endpoint/method not allowlisted")
        cookie_scope(self.session._jar)
        if headers is None:
            headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded;charset=utf-8", "X-Requested-With": "XMLHttpRequest", "page_info": json.dumps({"page_number": 1, "total_records_per_page": 20})}
        req = Request(url, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method=method)
        try:
            with self.session._opener.open(req, timeout=30) as r:
                if r.status not in (200, 202) or r.headers.get_content_type() != "application/json":
                    raise BoundaryError("Unexpected login/readback response; no retry")
                raw = r.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise BoundaryError("Login response size bound reached")
                j = json.loads(raw)
                # A changed response token needs confirmed rotation semantics before storage.
                rotated = r.headers.get("X-CSRF-Token")
                if rotated and rotated != self.session.context.csrf:
                    raise BoundaryError("Unexpected CSRF rotation; stop before persistence")
                cookie_scope(self.session._jar)
                return r.status, j
        except (HTTPError, URLError, TimeoutError, ValueError, UnicodeError):
            raise BoundaryError("Login/readback transport failed; details suppressed, no retry") from None

    @staticmethod
    def _body(status, raw):
        if status not in (200, 202) or not isinstance(raw, dict) or not isinstance(raw.get("headers"), dict) or raw["headers"].get("response_code") != "0000" or not isinstance(raw.get("body"), dict):
            raise BoundaryError("Authenticated readback not established; no storage or retry")
        return raw["body"]

    def login(self, login_name, password, *, approval_reference):
        if self.attempted:
            raise BoundaryError("One login attempt per process context; no retry or force logout")
        request = build_bootstrapped_login_request(self.session, login_name, password,
                                                   approval_reference=approval_reference)
        self.attempted = True
        status, raw = self._json(request.method, request.url, headers=request.headers, body=request.body)
        result = classify_login_response(status, raw)
        if result["outcome"] != "LOGIN_CLAIMS_SUCCESS_REQUIRE_SAME_SESSION_LOGINCHECK_AND_LOGINUSER_READBACK":
            raise BoundaryError(result["outcome"] + "; stop without retry, storage or force logout")
        status, raw = self._json("GET", LOGINCHECK)
        self._body(status, raw)
        status, raw = self._json("GET", LOGINUSER)
        user = self._body(status, raw).get("user")
        if not isinstance(user, dict) or type(user.get("customerid")) is not int or user["customerid"] <= 0:
            raise BoundaryError("Positive authenticated customer identity not established")
        names = [user.get("loginname"), user.get("email")]
        expected = login_name.strip().casefold()
        if not expected or expected not in {n.strip().casefold() for n in names if isinstance(n, str) and n.strip()}:
            raise BoundaryError("Authenticated identity differs from entered account; no storage")
        cookies = []
        for c in self.session._jar:
            cookies.append({"version": c.version, "name": c.name, "value": c.value,
                            "port": c.port, "port_specified": c.port_specified,
                            "domain": c.domain, "domain_specified": c.domain_specified,
                            "domain_initial_dot": c.domain_initial_dot,
                            "path": c.path, "path_specified": c.path_specified,
                            "secure": c.secure, "expires": c.expires, "discard": c.discard,
                            "rest": dict(c._rest)})
        identity = hashlib.sha256(json.dumps([user["customerid"], expected]).encode()).hexdigest()
        bundle = {"schema": 1, "tenant": "atlantadprca", "origin": BASE,
                  "cookies": cookies, "csrf": self.session.context.csrf,
                  "csrf_provenance": "normal sign-in HTML, same process jar",
                  "issued_at": datetime.now(timezone.utc).isoformat(),
                  "identity_hash": identity, "authenticated_readback_verified": True}
        return VerifiedSession(bundle)


def login_and_optionally_store(login_name, password, *, approval_reference,
                               approve_storage=False, session=None, store=None):
    # Supplying a session allows CLI bootstrap/security review BEFORE secret input.
    context = session or acquire_anonymous_bootstrap()
    verified = NormalLogin(context).login(login_name, password, approval_reference=approval_reference)
    if approve_storage:
        if store is None:
            from .auth import Keychain
            store = Keychain(service=SERVICE, account=ACCOUNT).store
        store(verified._bundle)
    result = verified.diagnostics()
    result["session_stored"] = bool(approve_storage)
    if approve_storage:
        result["storage"] = {"type": "macOS Keychain", "service": SERVICE, "account": ACCOUNT}
    return result
