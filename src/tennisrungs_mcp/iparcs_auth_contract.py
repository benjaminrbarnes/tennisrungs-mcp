"""Legacy offline builder and current login plan; never dispatches requests here.

Use iparcs_login with its fresh bootstrap for separately approved normal login.
Authenticated session issuance is not live verified.
"""
from dataclasses import dataclass, field

from .iparcs_consumer import BASE, BoundaryError


@dataclass(frozen=True)
class LoginRequest:
    method: str = "POST"
    url: str = BASE + "/rest/user/signin"
    headers: dict = field(default_factory=dict, repr=False)
    body: dict = field(default_factory=dict, repr=False)


def build_login_request(login_name, password, csrf_token, *, approval_reference):
    """Pure in-memory request construction. No token acquisition or dispatch."""
    if not approval_reference:
        raise BoundaryError("Separate iParcs credential setup approval required")
    if not all(isinstance(v, str) and v for v in [login_name, password, csrf_token]):
        raise BoundaryError("Verified normal login context and local credential input required")
    return LoginRequest(headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": csrf_token},
                        body={"login_name": login_name, "password": password, "signin_source_app": "0"})


def prompt_local_credentials(*, approval_reference):
    """Local non-echo handoff; no MCP credential input."""
    if not approval_reference:
        raise BoundaryError("Separate iParcs credential entry approval required")
    from .cli import prompt_credentials
    return prompt_credentials("Atlanta iParcs")


def assess_login_response(http_status, raw):
    """Source-specific classification; still no dispatch, retry or storage permission."""
    from .iparcs_login_bootstrap import classify_login_response
    return classify_login_response(http_status, raw)


def auth_plan():
    return {
        "mode": "auth_plan_only", "live_execution_enabled": False,
        "normal_login_source_observed": True, "normal_login_live_verified": False,
        "method": "POST", "url": BASE + "/rest/user/signin?locale=en-US",
        "body_field_names": ["login_name", "password", "signin_source_app", "locale", "ak_properties"],
        "normal_source_app": "0", "confirmed_csrf_header": "X-CSRF-Token",
        "credential_entry": "local non-echo prompt only after separate approval; no tool/model secret output",
        "storage_proposal": {"service": "tennis-iparcs", "account": "atlantadprca-consumer-session", "values": "new session cookies, CSRF and tenant/expiry metadata; never password"},
        "anonymous_bootstrap_live_verified": True,
        "bootstrap_flow": "GET /signin -> 302 /signin?locale=en-US -> 200 HTML window.__csrfToken; same in-memory jar",
        "duplicate_login_error_type": 12,
        "cookies_issued_before_login": True,
        "gaps": ["first approved sign-in and authenticated readback", "post-auth cookie issuance/rotation and CSRF enforcement", "actual effect on existing Ava session", "separate iParcs credential/storage approval"],
        "hard_stops": ["CAPTCHA", "unexpected waiver", "duplicate login", "force logout", "unknown cookie scope", "denied tool/site action"],
        "signin_dispatch_implemented": True, "signin_dispatch_live_verified": False,
        "keychain_configured": False,
    }
