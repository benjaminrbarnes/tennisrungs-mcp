from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from tennisrungs_mcp.iparcs_planning import preparation_plan, compare_cart
from tennisrungs_mcp.iparcs_preparation import TestPermission, parse_form
from tennisrungs_mcp.iparcs_consumer import BoundaryError
from tennisrungs_mcp.models import SafetyError
from test_iparcs_preparation import target, client, group, form, cart, NOW


def selection_dict():
    s = target()
    return {"resource_id": s.resource_id, "start": s.start, "end": s.end, "max_total": "15.00"}


def test_preparation_plan_no_dispatch_and_unknown_pattern_effects():
    r = preparation_plan(selection_dict(), NOW.isoformat())
    assert not r["live_execution_enabled"] and not r["payment_page_ready"]
    assert {"reserve", "checkout", "waiver", "deletion", "payment"} <= set(r["hard_denied"])
    assert all(not s["dispatch_enabled"] for s in r["stages"])
    assert "unverified preparation" in r["stages"][0]["effect"]


def test_cart_comparison_does_not_claim_live_browser_verification():
    t, summary = cart()
    r = compare_cart(selection_dict(), t, summary, t, summary,
                     "https://anc.apm.activecommunities.com/atlantadprca/newcart")
    assert r["comparison_passed"] and not r["live_browser_verified"]
    assert not r["final_payment_total_verified"] and not r["live_execution_enabled"]


def test_protected_permission_binds_selected_customer():
    c, f, _ = client()
    c.permission = replace(c.permission, customer_id=88)
    with pytest.raises(BoundaryError): c.select_and_validate()
    assert not f.calls


def test_semantic_pattern_failure_blocks_followup_mutation():
    bad = group(); bad["adjusted_message"] = "synthetic-adjustment"
    c, f, checkpoints = client([bad])
    with pytest.raises(BoundaryError): c.select_and_validate()
    assert c.ledger["uncertain"] and checkpoints[-1]["uncertain"]
    with pytest.raises(BoundaryError): c.prepare_cart_context()
    assert len(f.calls) == 1


def test_created_draft_readback_failure_is_unresolved():
    c, f, _ = client([{}, TimeoutError("synthetic")])
    c.group = group()
    with pytest.raises(BoundaryError): c.create_draft()
    assert c.ledger["uncertain"]
    with pytest.raises(BoundaryError): c.create_draft()
    assert len(f.calls) == 2


def test_unverified_event_update_cannot_advance():
    stale = form(); stale["reservation"]["event_name"] = "Different synthetic name"
    c, f, _ = client([stale]); c.draft = parse_form(55, form())
    with pytest.raises(BoundaryError): c.update_event_name()
    assert c.ledger["uncertain"] and len(f.calls) == 1


@pytest.mark.parametrize("changes", [{"resource_id": True}, {"attendees": True}, {"max_total": 15.0}, {"start": "2030-01-05T09:30:00.5"}])
def test_selection_schema_fails_closed(changes):
    with pytest.raises(BoundaryError): target(**changes).validate(NOW)


def test_cart_cap_nan_fails_safely_before_comparison():
    t, summary = cart()
    s = selection_dict(); s["max_total"] = "NaN"
    with pytest.raises(SafetyError): compare_cart(s, t, summary)
