"""Pure offline decision sketch. No network, browser, calendar, or Messages adapters.

This is a review aid for integration into the existing repository, not a runner.
Authority is supplied explicitly; historical prompts never grant it here.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class Intent:
    key: str
    start: datetime
    end: datetime
    venue: str
    cap_cents: int | None = None
    can_post: bool = False
    can_withdraw: bool = False
    can_book: bool = False
    can_calendar: bool = False
    can_message: bool = False
    calendar_id: str = ""
    recipient_ref: str = ""
    approved_text_hash: str = ""
    ladder_id: int | None = None
    season_team_id: int | None = None
    venue_id: int | None = None
    guard_buffer_minutes: int = 15
    deadline_guard: datetime | None = None
    poll_minutes: int = 60
    approval_check_hours: int = 12


@dataclass(frozen=True)
class Observation:
    fresh: bool = False
    complete: bool = False
    match_state: str = "ABSENT"
    exact_match: bool = False
    proposal_id: str = ""
    unknown_write: str = ""
    booking_state: str = "NONE"
    permit_id: str = ""
    checkout_cents: int | None = None
    obligation_known: bool = False
    checkout_exact: bool = False
    cart_isolated: bool = False
    payment_verified: bool = False
    calendar_reconciled: bool = False
    recipient_verified: bool = False
    recipient_ref: str = ""
    text_hash: str = ""
    message_state: str = "NONE"
    withdrawal_atomic: bool = False


@dataclass(frozen=True)
class Decision:
    action: str
    operation_key: str
    reason: str


def cutoffs(start: datetime, buffer_minutes: int = 15, override: datetime | None = None) -> tuple[datetime, datetime]:
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("Timezone-aware match start required")
    hard = start.astimezone(timezone.utc) - timedelta(hours=72)
    if type(buffer_minutes) is not int or not 0 <= buffer_minutes <= 1440:
        raise ValueError("Guard buffer must be nonnegative bounded integer minutes")
    guard = hard - timedelta(minutes=buffer_minutes)
    if override is not None:
        if override.tzinfo is None or override.utcoffset() is None:
            raise ValueError("Explicit guard requires a timezone")
        guard = override.astimezone(timezone.utc)
        if guard > hard:
            raise ValueError("Explicit guard cannot extend beyond the booking cutoff")
    return guard, hard


def reconcile(intent: Intent, obs: Observation, now: datetime) -> Decision:
    """Return at most one next step. Caller must journal and lock before any write.

    Assertions such as fresh/exact/atomic must come from verified adapters in a
    production system; caller-provided booleans are not proof of vendor behavior.
    """
    guard, hard = cutoffs(intent.start, intent.guard_buffer_minutes, intent.deadline_guard)
    if now.tzinfo is None or now.utcoffset() is None or intent.end.tzinfo is None or intent.end.utcoffset() is None:
        raise ValueError("Timezone-aware timestamps required")
    if intent.end.astimezone(timezone.utc) <= intent.start.astimezone(timezone.utc):
        raise ValueError("Positive match interval required")
    if intent.cap_cents is not None and (
        type(intent.cap_cents) is not int or intent.cap_cents < 0
    ):
        raise ValueError("Budget must be integer cents")

    def answer(action, reason):
        return Decision(action, f"{intent.key}:{action}", reason)

    if obs.unknown_write:
        return answer("RECONCILE_UNKNOWN", obs.unknown_write)
    if not obs.fresh or not obs.complete:
        return answer("REFRESH", "Fresh complete source evidence required")
    if not obs.exact_match:
        return answer("BLOCK", "Observed match differs from authorized scope")
    if obs.match_state == "WITHDRAWN":
        return answer("STOP", "Verified withdrawal; reconcile terminal jobs")
    if obs.match_state == "ABSENT":
        if now >= guard:
            return answer("BLOCK", "Conservative posting/booking guard reached")
        return answer("POST" if intent.can_post else "REVIEW", "Exact posting authority required")
    if not obs.proposal_id:
        return answer("BLOCK", "Stable proposal identity required")
    if obs.match_state == "PROPOSED":
        if now < guard:
            return answer("WAIT", "Use deterministic polling; no model loop")
        # Caller-supplied atomic=True is not vendor capability evidence. The repo
        # has no validated atomic withdrawal implementation, including offline plans.
        return answer("REVIEW_WITHDRAWAL", "Fresh reads alone do not eliminate acceptance race")
    if obs.match_state != "ACCEPTED":
        return answer("BLOCK", "Unknown match status")

    if obs.booking_state not in {"NONE", "QUOTED", "PAID_TENTATIVE", "APPROVED"}:
        return answer("BLOCK", "Unrecognized booking state")
    if obs.booking_state in {"NONE", "QUOTED"}:
        if now >= hard:
            return answer("BLOCK", "72-hour booking cutoff reached; preserve accepted match")
        if now >= guard:
            return answer("REVIEW_BOOKING", "Inside conservative buffer; do not cancel accepted match")
        if not intent.can_book or intent.cap_cents is None:
            return answer("REVIEW_BOOKING", "Explicit per-date booking authority and cap required")
        if obs.booking_state == "NONE":
            return answer("STAGE_BROWSER_BOOKING", "Existing reservation preparation boundary")
        if not all((obs.checkout_exact, obs.obligation_known, obs.cart_isolated, obs.payment_verified)):
            return answer("BLOCK", "Exact isolated checkout and financial obligation required")
        if type(obs.checkout_cents) is not int or obs.checkout_cents < 0:
            return answer("BLOCK", "Exact nonnegative integer-cent quote required")
        if obs.checkout_cents > intent.cap_cents:
            return answer("BLOCK", "This date exceeds its own cap")
        return answer("BOOKING_COMMIT_READY", "Journal ATTEMPTED before single submission")

    if not obs.permit_id:
        return answer("BLOCK", "Verified permit identity required")
    if intent.can_calendar and not obs.calendar_reconciled:
        if not intent.calendar_id:
            return answer("BLOCK", "Pinned calendar identity required")
        return answer("RECONCILE_CALENDAR", "Preserve pending title for PAID_TENTATIVE")
    if intent.can_message and obs.message_state != "VERIFIED":
        if obs.message_state != "NONE":
            return answer("RECONCILE_MESSAGE", "Uncertain send requires history readback")
        if not (obs.recipient_verified and intent.recipient_ref
                and obs.recipient_ref == intent.recipient_ref
                and intent.approved_text_hash and obs.text_hash == intent.approved_text_hash):
            return answer("BLOCK", "Verified recipient and exact approved message required")
        return answer("MESSAGE_COMMIT_READY", "Single imsg send followed by readback")
    return answer("CHECK_APPROVAL_AT_DUE_TIME" if obs.booking_state == "PAID_TENTATIVE" else "STOP",
                  "Tentative is distinct from approved; no checkout reopening")
