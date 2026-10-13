"""Offline affordances only. No PreparationClient or transport is constructed."""
from dataclasses import asdict
from decimal import Decimal, InvalidOperation

from .iparcs_preparation import Selection, EFFECTS, parse_cart, handoff, verify_browser_handoff
from .models import SafetyError
from .workflow_api import timestamp


def selection_input(values):
    if not isinstance(values, dict):
        raise SafetyError("Selection must be structured local input")
    data = dict(values)
    if data.get("max_total") is not None:
        if not isinstance(data["max_total"], str):
            raise SafetyError("Exact decimal cap must be a string; no floating-point money")
        try:
            data["max_total"] = Decimal(data["max_total"])
        except InvalidOperation:
            raise SafetyError("Invalid decimal cap") from None
        if not data["max_total"].is_finite() or data["max_total"] < 0:
            raise SafetyError("Cap must be finite and nonnegative")
    return Selection(**data)


def preparation_plan(selection: dict, now: str):
    s = selection_input(selection)
    s.validate(timestamp(now))
    return {
        "mode": "offline_contract_plan", "live_execution_enabled": False,
        "protected_contracts_live_verified": False, "target_key": s.key,
        "resource_id": s.resource_id, "start": s.start, "end": s.end,
        "attendees": s.attendees, "explicit_cap": str(s.max_total) if s.max_total is not None else None,
        "stages": [{"name": name, "effect": effect, "dispatch_enabled": False}
                   for name, effect in EFFECTS.items()],
        "required_before_live_test": ["separate iParcs credential approval", "verified selected customer", "exact direct user target permission", "durable checkpoint", "sanitized protected-schema verification"],
        "hard_denied": ["reserve", "checkout", "waiver", "deletion", "payment", "force_logout"],
        "payment_page_ready": False,
        "blocker": "Selection/validation may have server effects; checkout can finalize a zero-payment request",
    }


def compare_cart(selection: dict, transactions: dict, summary: dict,
                 browser_transactions=None, browser_summary=None, browser_url=None):
    s = selection_input(selection)
    snapshot = parse_cart(transactions, summary)
    h = handoff(s, snapshot)
    compared = False
    if any(v is not None for v in [browser_transactions, browser_summary, browser_url]):
        if any(v is None for v in [browser_transactions, browser_summary, browser_url]):
            raise SafetyError("Independent browser comparison needs all three inputs")
        compared = verify_browser_handoff(h, parse_cart(browser_transactions, browser_summary), browser_url)
    return {
        "mode": "offline_snapshot_comparison", "live_execution_enabled": False,
        "live_browser_verified": False, "comparison_passed": compared,
        "target_key": h.target_key, "fingerprint": h.expected_fingerprint,
        "due_now": str(snapshot.due_now), "currency": snapshot.currency,
        "candidate_url": h.url, "existing_checkout_state_claimed": h.payment_page_ready,
        "final_payment_total_verified": False, "blocker": h.blocker,
    }
