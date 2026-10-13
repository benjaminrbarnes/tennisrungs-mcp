"""Verified anonymous consumer bootstrap; no sign-in dispatcher or persistent store.

Only public GET /signin and its exact locale redirect are sent. Secret bootstrap
values stay in this process; callers receive metadata or an in-memory request.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

from .iparcs_consumer import BASE, BoundaryError

HOST = "anc.apm.activecommunities.com"
SIGNIN = BASE + "/signin"
FINAL_SIGNIN = SIGNIN + "?locale=en-US"
COOKIE_NAMES = {
    "JSESSIONID", "atlantadprca_JSESSIONID", "atlantadprca_LOGGED_JSESSIONID",
    "atlantadprca_FullPageView", "atlantadprca_NEW_CUI_STATUS", "NEED_VERIFY_RECAPTCHA",
    "BIGipServer~activenet~anc_prod_atlantadprca",
    "BIGipServer~activenet~activenet_newcui_prod_pool_ats",
}


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.inside = False; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == "script": self.inside = not dict(attrs).get("src")
    def handle_endtag(self, tag):
        if tag == "script": self.inside = False
    def handle_data(self, data):
        if self.inside: self.parts.append(data)


def literal(script: str, variable: str) -> str:
    matches = re.findall(r"window\." + re.escape(variable) + r"\s*=\s*(\"(?:[^\"\\]|\\.)*\"|'[^'\\]*')\s*;", script)
    if len(matches) != 1:
        raise BoundaryError("Expected one static bootstrap literal; do not evaluate JavaScript")
    raw = matches[0]
    return json.loads(raw) if raw.startswith('"') else raw[1:-1]


def flag(script: str, name: str, *, boolean: bool) -> bool | int:
    values = set(re.findall(r'"' + re.escape(name) + r'"\s*:\s*(true|false|[0-9]+)',script))
    if len(values) != 1:
        raise BoundaryError("Missing/conflicting login security configuration")
    value=values.pop()
    if boolean:
        if value not in {"true","false"}: raise BoundaryError("Invalid security configuration type")
        return value == "true"
    if not value.isdigit(): raise BoundaryError("Invalid security configuration type")
    return int(value)


@dataclass(frozen=True)
class Bootstrap:
    csrf: str = field(repr=False)
    account_recaptcha_enabled: bool
    recaptcha_failed_count: int
    challenge_marker: bool
    version: str
    authenticated: bool = False  # Cookie names never establish authentication.

    @property
    def first_attempt_requires_recaptcha(self) -> bool:
        return self.account_recaptcha_enabled and (self.recaptcha_failed_count == 0 or self.challenge_marker)


def parse_bootstrap(html: str, final_url: str, *, challenge_marker: bool = False) -> Bootstrap:
    if final_url != FINAL_SIGNIN:
        raise BoundaryError("Unexpected sign-in URL; no login request may be constructed")
    if not isinstance(html,str) or len(html.encode()) > 1024*1024:
        raise BoundaryError("Sign-in page missing or larger than bounded bootstrap")
    parser=Scripts();parser.feed(html);source="\n".join(parser.parts)
    if literal(source,"__siteBaseName") != "/atlantadprca":
        raise BoundaryError("Unexpected tenant bootstrap")
    token=literal(source,"__csrfToken")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,512}",token):
        raise BoundaryError("Unexpected CSRF format")
    version=literal(source,"__version")
    if not re.fullmatch(r"[0-9.]{1,32}",version):raise BoundaryError("Unexpected version format")
    return Bootstrap(token,flag(source,"enable_recaptcha_for_account",boolean=True),
                     flag(source,"enable_recaptcha_failed_count",boolean=False),challenge_marker,version)


def cookie_scope(jar: http.cookiejar.CookieJar) -> list[dict]:
    """Metadata only. Keep the fresh process's complete bounded first-party jar."""
    result=[]
    for cookie in jar:
        if (cookie.domain.lstrip(".") not in {HOST,"apm.activecommunities.com"}
                or cookie.path not in {"/","/atlantadprca","/atlantadprca/"}
                or (cookie.name not in COOKIE_NAMES and not re.fullmatch(r"TS[0-9a-fA-F]{8}",cookie.name))):
            raise BoundaryError("Unknown cookie scope; stop before credential transmission/persistence")
        if cookie.name == "JSESSIONID" and cookie.domain.lstrip(".") != HOST:
            raise BoundaryError("Generic session cookie has unexpected broad domain")
        result.append({"name":cookie.name,"domain":cookie.domain,"path":cookie.path,
                       "secure":cookie.secure,"http_only":any(k.lower()=="httponly" for k in cookie._rest),
                       "session_cookie":cookie.expires is None})
    if not {"JSESSIONID","atlantadprca_JSESSIONID","atlantadprca_LOGGED_JSESSIONID"}.issubset({r["name"] for r in result}):
        raise BoundaryError("Normal anonymous session cookie context missing")
    return result


class ExactSignInRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.full_url != SIGNIN or code != 302 or newurl != FINAL_SIGNIN:
            raise BoundaryError("Unexpected bootstrap redirect; do not follow another origin or flow")
        return super().redirect_request(req,fp,code,msg,headers,newurl)


@dataclass
class AnonymousLoginSession:
    context: Bootstrap
    _jar: http.cookiejar.CookieJar = field(repr=False)
    _opener: object = field(repr=False)

    def diagnostics(self) -> dict:
        return {"tenant":"atlantadprca","version":self.context.version,
                "csrf_bootstrap_verified":True,"authenticated_session_verified":False,
                "first_attempt_requires_recaptcha":self.context.first_attempt_requires_recaptcha,
                "cookie_metadata":cookie_scope(self._jar),"persistent_storage_created":False}


def acquire_anonymous_bootstrap() -> AnonymousLoginSession:
    jar=http.cookiejar.CookieJar()
    opener=build_opener(ExactSignInRedirect(),HTTPCookieProcessor(jar))
    try:
        with opener.open(Request(SIGNIN,headers={"Accept":"text/html"}),timeout=30) as response:
            if response.status != 200 or response.headers.get_content_type() != "text/html":
                raise BoundaryError("Unexpected public sign-in response")
            payload=response.read(1024*1024+1)
            if len(payload)>1024*1024:raise BoundaryError("Bootstrap size bound reached")
            html=payload.decode("utf-8")
            marker=any(c.name=="NEED_VERIFY_RECAPTCHA" and c.value not in {"","0"} for c in jar)
            context=parse_bootstrap(html,response.url,challenge_marker=marker)
        cookie_scope(jar)
        return AnonymousLoginSession(context,jar,opener)
    except (HTTPError,URLError,UnicodeError,ValueError,TimeoutError):
        raise BoundaryError("Anonymous bootstrap failed; details suppressed") from None


@dataclass(frozen=True)
class BootstrappedLoginRequest:
    url: str = BASE + "/rest/user/signin?locale=en-US"
    method: str = "POST"
    headers: dict = field(default_factory=dict,repr=False)
    body: dict = field(default_factory=dict,repr=False)


def build_bootstrapped_login_request(session: AnonymousLoginSession, login_name: str, password: str,
                                    *, approval_reference: str) -> BootstrappedLoginRequest:
    """Pure construction. Owner must dispatch at most once on THIS session's opener/jar."""
    if not isinstance(approval_reference,str) or not approval_reference.strip():
        raise BoundaryError("Separate iParcs credential-transmission approval required")
    if not all(isinstance(v,str) and v for v in [login_name,password]):
        raise BoundaryError("Approved local non-echo credential input required")
    cookie_scope(session._jar)
    if session.context.first_attempt_requires_recaptcha:
        raise BoundaryError("Normal frontend requires reCAPTCHA; no plain credential request allowed")
    return BootstrappedLoginRequest(headers={"Content-Type":"application/json","X-Requested-With":"XMLHttpRequest",
            "X-CSRF-Token":session.context.csrf,"page_info":json.dumps({"page_number":1,"total_records_per_page":20})},
            body={"login_name":login_name,"password":password,"signin_source_app":"0",
                  "locale":"en-US","ak_properties":None})


def classify_login_response(http_status: int, raw: object) -> dict:
    """Source-specific flags with no response text, credentials, tokens or URLs exposed."""
    safe=dict(authenticated_session_verified=False,storage_allowed=False,retry_allowed=False)
    def stop(outcome):return dict(safe,outcome=outcome)
    if http_status not in (200,202):return stop("STOP_HTTP_BOUNDARY")
    if not isinstance(raw,dict) or not isinstance(raw.get("headers"),dict) or raw["headers"].get("response_code") != "0000":
        return stop("STOP_APPLICATION_BOUNDARY")
    body=raw.get("body");result=body.get("result") if isinstance(body,dict) else None
    if not isinstance(result,dict) or set(body)-{"result"}:return stop("STOP_UNKNOWN_SCHEMA")
    kind=result.get("error_type")
    if isinstance(kind,bool) or kind is not None and not isinstance(kind,(str,int)):
        return stop("STOP_UNKNOWN_ERROR_TYPE")
    if kind in (12,"12"):return stop("STOP_DUPLICATE_LOGIN_PRESERVE_EXISTING_SESSION")
    if kind in (11,"11"):return stop("STOP_COLLECT_EMAIL_FLOW")
    if kind in (10,"10",1,"1"):return stop("STOP_ACCOUNT_ACTIVATION_FLOW")
    if kind in (7,"7"):return stop("STOP_EXTERNAL_REDIRECT_FLOW")
    if result.get("need_verify_recaptcha") is not False or kind in (2,"2"):
        return stop("STOP_RECAPTCHA_OR_UNKNOWN_SECURITY_FLOW")
    if result.get("security_sign_token") or result.get("public_customer_id"):
        return stop("STOP_CUSTOMIZED_WAIVER_OR_PARTIAL_SIGNING_FLOW")
    if result.get("redirect_url"):return stop("STOP_REDIRECT_FLOW")
    if result.get("campaign_id",-1) != -1:return stop("STOP_DONATION_FLOW")
    known={"success","message","error_type","need_verify_recaptcha","security_sign_token","public_customer_id",
           "redirect_url","campaign_id","ak_update_succeed","access_token"}
    if set(result)-known or result.get("access_token") or result.get("ak_update_succeed") not in (None,False):
        return stop("STOP_UNEXPECTED_FLOW")
    if result.get("success") is not True or kind not in (None,"",0,"0"):
        return stop("STOP_LOGIN_FAILURE")
    return stop("LOGIN_CLAIMS_SUCCESS_REQUIRE_SAME_SESSION_LOGINCHECK_AND_LOGINUSER_READBACK")
