"""Source-derived OFFLINE login helper; no network/Keychain implementation.

Normal login context and safe session issuance are not yet verified. Never turn
this contract into a login dispatcher merely because a mock accepts its body.
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
    """Future local handoff helper; intentionally not wired to CLI/MCP login."""
    if not approval_reference:
        raise BoundaryError("Separate iParcs credential entry approval required")
    from .cli import prompt_credentials
    return prompt_credentials("Atlanta iParcs")


def assess_login_response(http_status, raw):
    """Return only a safe stop classification, never cookies, messages or redirect URLs."""
    stop = {"authenticated_session_verified": False, "storage_allowed": False, "retry_allowed": False}
    if http_status != 200:
        return dict(stop, outcome="STOP_HTTP_OR_SECURITY_BOUNDARY")
    if not isinstance(raw, dict) or not isinstance(raw.get("headers"), dict) or raw["headers"].get("response_code") != "0000":
        return dict(stop, outcome="STOP_APPLICATION_OR_UNKNOWN_SCHEMA")
    body = raw.get("body")
    result = body.get("result") if isinstance(body, dict) else None
    if not isinstance(result, dict):
        return dict(stop, outcome="STOP_UNKNOWN_LOGIN_SCHEMA")
    if result.get("need_verify_recaptcha") is not False:
        return dict(stop, outcome="STOP_CAPTCHA_OR_UNKNOWN_SECURITY_FLOW")
    known = {"success", "message", "error_type", "need_verify_recaptcha"}
    if set(result) - known or set(body) - {"result"}:
        return dict(stop, outcome="STOP_UNEXPECTED_WAIVER_REDIRECT_OR_FLOW")
    if result.get("success") is not True or result.get("error_type") not in (None, "", 0):
        # Includes duplicate-login errors. Never force logout or retry with flags.
        return dict(stop, outcome="STOP_LOGIN_FAILURE_OR_DUPLICATE")
    return dict(stop, outcome="LOGIN_RESPONSE_CLAIMS_SUCCESS_SESSION_SCOPE_UNVERIFIED")


def auth_plan():
    return {
        "mode": "offline_auth_contract", "live_execution_enabled": False,
        "normal_login_source_observed": True, "normal_login_live_verified": False,
        "method": "POST", "url": BASE + "/rest/user/signin",
        "body_field_names": ["login_name", "password", "signin_source_app"],
        "normal_source_app": "0", "candidate_csrf_header": "X-CSRF-Token",
        "credential_entry": "local non-echo prompt only after separate approval; no tool/model secret output",
        "storage_proposal": {"service": "tennis-iparcs", "account": "atlantadprca-consumer-session", "values": "new session cookies, CSRF and tenant/expiry metadata; never password"},
        "gaps": ["exact fresh anonymous CSRF/bootstrap acquisition contract", "smallest sufficient tenant-bound cookie/routing set", "legal waiver and redirect schema", "duplicate-login semantics and impact on existing Ava session", "authenticated logincheck/read-back validation", "separate iParcs storage approval"],
        "hard_stops": ["CAPTCHA", "unexpected waiver", "duplicate login", "force logout", "unknown cookie scope", "denied tool/site action"],
        "signin_dispatch_implemented": False, "keychain_configured": False,
    }
