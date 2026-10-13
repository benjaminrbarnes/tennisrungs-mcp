import pytest

from tennisrungs_mcp.iparcs_auth_contract import build_login_request, assess_login_response, auth_plan
from tennisrungs_mcp.iparcs_consumer import BoundaryError


def response(**changes):
    result = {"success": True, "message": "", "error_type": "", "need_verify_recaptcha": False}
    result.update(changes)
    return {"headers": {"response_code": "0000"}, "body": {"result": result}}


def test_exact_minimal_login_contract_no_force_or_secret_repr():
    request = build_login_request("synthetic-user", "synthetic-secret-marker", "synthetic-csrf-marker", approval_reference="synthetic-only")
    assert request.body == {"login_name": "synthetic-user", "password": "synthetic-secret-marker", "signin_source_app": "0"}
    assert "synthetic-secret-marker" not in repr(request) and "synthetic-csrf-marker" not in repr(request)
    assert "force_logged_off" not in request.body


def test_no_approval_or_csrf_context_fails_closed():
    with pytest.raises(BoundaryError):
        build_login_request("synthetic", "synthetic", "", approval_reference="synthetic")
    with pytest.raises(BoundaryError):
        build_login_request("synthetic", "synthetic", "synthetic", approval_reference="")


@pytest.mark.parametrize("raw", [response(need_verify_recaptcha=True), response(waiver_required=True), response(redirect_url="https://example.invalid"), response(success=False, error_type="duplicate_login")])
def test_security_or_unexpected_flow_never_stores_or_retries(raw):
    r = assess_login_response(200, raw)
    assert not r["storage_allowed"] and not r["retry_allowed"] and r["outcome"].startswith("STOP")


def test_claimed_success_is_not_validated_cookie_scope():
    r = assess_login_response(200, response())
    assert not r["authenticated_session_verified"] and not r["storage_allowed"]


def test_auth_plan_does_not_construct_credentials_or_signin_runtime():
    p = auth_plan()
    assert p["signin_dispatch_implemented"] and not p["signin_dispatch_live_verified"]
    assert not p["keychain_configured"] and not p["live_execution_enabled"]
