"""Pure planning/result boundary. It never invokes live adapters or creates jobs."""
import hashlib
import json
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta, timezone

from .journal import Journal
from .models import SafetyError
from .workflow import Intent, Observation, cutoffs, reconcile


def timestamp(value):
    if not isinstance(value, str):
        raise SafetyError("An explicit ISO timestamp with timezone is required")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise SafetyError("Invalid ISO timestamp") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise SafetyError("Timestamp must include an explicit UTC offset")
    return dt


def typed(cls, values):
    if not isinstance(values, dict) or set(values) - {f.name for f in fields(cls)}:
        raise SafetyError("Unrecognized planning input fields")
    return cls(**values)


def plan(intent: dict, observation: dict, now: str, *, journal_record=None):
    data = dict(intent)
    data["start"], data["end"] = timestamp(data.get("start")), timestamp(data.get("end"))
    if data.get("deadline_guard") is not None:
        data["deadline_guard"] = timestamp(data["deadline_guard"])
    i, o, current = typed(Intent, data), typed(Observation, observation), timestamp(now)
    if not isinstance(i.key, str) or not 1 <= len(i.key) <= 64 or not isinstance(i.venue, str) or not 1 <= len(i.venue) <= 256:
        raise SafetyError("Bounded intent identity and venue are required")
    for value in [i.calendar_id, i.recipient_ref, i.approved_text_hash,
                  o.match_state, o.proposal_id, o.unknown_write, o.booking_state,
                  o.permit_id, o.recipient_ref, o.text_hash, o.message_state]:
        if not isinstance(value, str) or len(value) > 256:
            raise SafetyError("Planning state and identity references must be bounded strings")
    for name in ["can_post", "can_withdraw", "can_book", "can_calendar", "can_message"]:
        if type(getattr(i, name)) is not bool:
            raise SafetyError("Planning grants must be explicit booleans, not verified authority")
    for name in ["fresh", "complete", "exact_match", "obligation_known", "checkout_exact", "cart_isolated", "payment_verified", "calendar_reconciled", "recipient_verified", "withdrawal_atomic"]:
        if type(getattr(o, name)) is not bool:
            raise SafetyError("Observation assertions must be booleans")
    for name in ["ladder_id", "season_team_id", "venue_id"]:
        value = getattr(i, name)
        if value is not None and (type(value) is not int or value <= 0):
            raise SafetyError("Optional season/venue IDs must be positive integers")
    if type(i.poll_minutes) is not int or not 60 <= i.poll_minutes <= 1440 or type(i.approval_check_hours) is not int or not 1 <= i.approval_check_hours <= 168:
        raise SafetyError("Invalid bounded planning cadence")
    canonical = asdict(i)
    for name in ["start", "end", "deadline_guard"]:
        dt = canonical[name]
        canonical[name] = dt.astimezone(timezone.utc).isoformat() if dt else None
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    journal_state = journal_record.get("state") if journal_record else None
    if journal_record and journal_record.get("challenge_id") is not None and o.proposal_id and str(journal_record["challenge_id"]) != str(o.proposal_id):
        raise SafetyError("Journal target does not match the supplied observation")
    if journal_state in ["ATTEMPTED", "ACKNOWLEDGED", "UNKNOWN"]:
        o = replace(o, unknown_write="unresolved operation journal")
    elif journal_state in ["VERIFIED", "REJECTED"]:
        # A local record is not fresh source verification. Preserve journal state;
        # refuse a new commitment recommendation from reconciliation alone.
        o = replace(o, fresh=False)
    elif journal_record is not None:
        raise SafetyError("Unrecognized journal state; no replay assumption")
    decision = reconcile(i, o, current)
    guard, hard = cutoffs(i.start, i.guard_buffer_minutes, i.deadline_guard)
    next_due = None
    if decision.action == "WAIT":
        next_due = min(current.astimezone(timezone.utc) + timedelta(minutes=i.poll_minutes), guard)
    elif decision.action == "CHECK_APPROVAL_AT_DUE_TIME":
        next_due = i.start.astimezone(timezone.utc) - timedelta(hours=i.approval_check_hours)
    return {
        "mode": "offline_plan", "live_execution_enabled": False,
        "authority_verified": False, "source_assertions_verified": False,
        "intent_hash": digest,
        "decision": {"action": decision.action, "operation_key": f"workflow:{decision.action}:{digest[:32]}",
                     "reason": decision.reason if decision.action != "RECONCILE_UNKNOWN" else "Unresolved attempt requires source read-back; never retry"},
        "start_utc": i.start.astimezone(timezone.utc).isoformat(),
        "end_utc": i.end.astimezone(timezone.utc).isoformat(),
        "guard_utc": guard.isoformat(), "hard_cutoff_utc": hard.isoformat(),
        "guard_policy": "explicit_preserved" if i.deadline_guard else f"{i.guard_buffer_minutes}_minute_buffer",
        "next_due_at": next_due.isoformat() if next_due else None,
        "check_due_now": bool(next_due and next_due <= current.astimezone(timezone.utc)),
        "timer_installed": False, "journal_state": journal_state,
        "required_live_adapters": ["verified authority", "fresh account observations", "durable dispatcher/outbox", "calendar discovery", "recipient verification"],
    }


def reconcile_local(intent, observation, now, journal_path, operation_key):
    record = Journal.inspect_existing(journal_path, operation_key)
    result = plan(intent, observation, now, journal_record=record)
    result["journal_operation_found"] = record is not None
    result["journal_modified"] = False
    return result
