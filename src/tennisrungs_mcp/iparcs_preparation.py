"""Offline-tested consumer preparation contracts; no credential configuration.

Inject a separately approved authenticated Transport. No live mutating request was
validated. Checkout, reserve, waivers, deletion and payment are hard-denied.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import urlparse

from .iparcs_consumer import BASE, BoundaryError, Transport, guard_deadline, local_instant, unwrap

UTC = timezone.utc


@dataclass(frozen=True)
class Selection:
    resource_id: int
    start: str
    end: str
    attendees: int = 2
    event_type_id: int = 27
    event_name: str = "Tennis"
    max_total: Decimal | None = None  # No cap is inferred from preparation permission.

    def validate(self, now: datetime) -> None:
        a, b = local_instant(self.start), local_instant(self.end)
        if now.tzinfo is None or now.utcoffset() is None or type(self.resource_id) is not int or self.resource_id <= 0 or type(self.attendees) is not int or not 1 <= self.attendees <= 4:
            raise BoundaryError("Invalid target or timezone")
        if a.date() != b.date() or a.second or b.second or a.microsecond or b.microsecond or a.minute % 5 or b.minute % 5:
            raise BoundaryError("Only exact same-day five-minute tennis increments are implemented")
        if b.astimezone(UTC) <= a.astimezone(UTC):
            raise BoundaryError("Invalid target range")
        if now.astimezone(UTC) >= guard_deadline(a).astimezone(UTC):
            raise BoundaryError("Rolling 72-hour plus 15-minute guard reached")
        if (a.date()-now.astimezone(a.tzinfo).date()).days > 90:
            raise BoundaryError("Beyond site 90-day reservation horizon")
        if type(self.event_type_id) is not int or self.event_type_id != 27 or not isinstance(self.event_name, str) or not self.event_name.strip() or len(self.event_name) > 256:
            raise BoundaryError("This preparation contract is scoped to Tennis")
        if self.max_total is not None and (not isinstance(self.max_total, Decimal) or not self.max_total.is_finite() or self.max_total < 0):
            raise BoundaryError("Invalid explicit cap")
        wire_datetime(self.start); wire_datetime(self.end)

    @property
    def key(self) -> str:
        # Includes per-date budget and attendees, preventing permission reuse for changed scope.
        raw = (self.resource_id, self.start, self.end, self.attendees, self.event_type_id,
               self.event_name, str(self.max_total))
        return hashlib.sha256(json.dumps(raw).encode()).hexdigest()


def wire_datetime(value: str) -> str:
    agency = local_instant(value)
    wall = agency.replace(tzinfo=None).isoformat()
    # Wire contract has no offset; don't erase an explicit DST fold distinction.
    local_instant(wall)
    return wall.replace("T", " ")


@dataclass(frozen=True)
class TestPermission:
    """An explicit target-specific approval supplied by the orchestrator, never auto-created."""
    selection_key: str
    allowed_operations: frozenset[str]
    expires: datetime
    approval_reference: str
    acknowledges_unknown_hold_or_draft_effects: bool = False
    customer_id: int | None = None
    __test__ = False


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    path: str
    body: dict | None = field(default=None, repr=False)
    effect: str = "read"


EFFECTS = {
    "patterns": "unverified preparation; may write selection/session state; hold unknown",
    "validate": "unverified preparation; may alter selection/draft; hold unknown",
    "proceed": "draft/mini-cart creation or change; hold and staff-notification behavior unknown",
    "event_type": "draft write; changes event rules/questions/waivers and fees",
    "event_name": "draft write",
    "cart_context": "GET preparation initializes cart context; side effects unknown",
}


def forbidden(op: Operation) -> bool:
    bare = op.path.split("?", 1)[0]
    return (op.method == "DELETE" or bare.startswith("/rest/checkout")
            or bare in {"/rest/common/signwaivers", "/rest/user/signin"}
            or "/reserve/" in bare or bare.endswith("/reservenow")
            or "quickreservation" in bare or "creditcard" in bare or "payment" in bare)


def exact_group(selection: Selection, body: dict) -> dict:
    """Normalize the old page's one-slot selection mapping (modules 442445/818085).

    Old frontend creates local booking_ counters, separate from returned identifiers.
    Server group ID/summary are preserved. No adjusted or partial selections accepted.
    """
    groups = body.get("reservation_time_groups")
    group = groups[0] if isinstance(groups, list) and len(groups) == 1 else body
    times = group.get("reservation_times", [])
    if group.get("availability") != "Available" or group.get("adjusted_message"):
        raise BoundaryError("Selection is partial, adjusted or unavailable")
    if len(times) != 1 or times[0].get("availability") != "Available":
        raise BoundaryError("Exactly one fully available reservation interval required")
    time = times[0]
    if (wire_datetime(time["start_event_datetime"]), wire_datetime(time["end_event_datetime"])) != (
            wire_datetime(selection.start), wire_datetime(selection.end)):
        raise BoundaryError("Server changed the requested interval")
    if "group_id" not in group:
        raise BoundaryError("Missing server group ID")
    return {"group_id": group["group_id"], "summary": group.get("summary", ""),
            "short_summary": group.get("short_summary", ""), "adjusted_message": "",
            "availability": "Available", "reservation_times": [{
                "start_event_datetime": time["start_event_datetime"],
                "end_event_datetime": time["end_event_datetime"],
                "availability": "Available", "booking_identifier": "booking_1"}]}


@dataclass
class Draft:
    reno: int
    timestamp: Any
    raw: dict = field(repr=False)


def parse_form(reno: int, body: dict) -> Draft:
    if type(reno) is not int or reno <= 0 or "timestamp" not in body or body["timestamp"] is None:
        raise BoundaryError("Missing draft identity/concurrency timestamp")
    if "reservation" not in body or "event_fee" not in body:
        raise BoundaryError("Unexpected consumer form schema; sanitized live verification needed")
    return Draft(reno, body["timestamp"], copy.deepcopy(body))


def verify_form_selection(draft: Draft, selection: Selection, customer_id: int) -> None:
    reservation = draft.raw["reservation"]
    resources = reservation.get("resources", [])
    if (reservation.get("customer_id") != customer_id or reservation.get("company_id",0) != 0
            or len(resources) != 1 or resources[0].get("resource_id") != selection.resource_id):
        raise BoundaryError("Form participant/resource differs from the exact target")
    schedules = resources[0].get("schedules", [])
    if len(schedules) != 1:
        raise BoundaryError("Form must contain exactly one schedule")
    schedule = schedules[0]
    # Source ScheduleList module 561628 consumes these fields after key casing conversion.
    if (wire_datetime(schedule.get("start_event_datetime","")),wire_datetime(schedule.get("end_event_datetime","")),
            schedule.get("attendance")) != (wire_datetime(selection.start),wire_datetime(selection.end),selection.attendees):
        raise BoundaryError("Form schedule/time/attendance differs from target")


class PreparationClient:
    """Explicit operations and write-ahead checkpoints; never retry an uncertain mutation.

    checkpoint() must durably save the sanitized ledger before a live mutation.
    The default denies mutation because no durable sink or permission is configured.
    """
    def __init__(self, transport: Transport, selection: Selection, *,
                 permission: TestPermission | None = None, ledger: dict | None = None,
                 checkpoint: Callable[[dict], None] | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.transport, self.selection, self.permission = transport, selection, permission
        self.ledger = ledger if ledger is not None else {}
        self.checkpoint, self.clock = checkpoint, clock
        self.customer_id = 0
        self.draft: Draft | None = None
        self.group: dict | None = None

    def execute(self, op: Operation) -> dict:
        if forbidden(op):
            raise BoundaryError("Submission/payment/security endpoint is hard-denied")
        routes = {
            "logincheck": ("GET", "/rest/common/logincheck"),
            "mini_cart": ("GET", "/rest/reservation/minishoppingcart"),
            "form_context": ("POST", f"/rest/reservation/resource/detail/{self.selection.resource_id}/formdata"),
            "patterns": ("POST", "/rest/reservation/resource/reservationtimegroup"),
            "validate": ("POST", "/rest/reservation/resource/validation"),
            "proceed": ("POST", "/rest/reservation/resource/proceed"),
            "event_type": ("PUT", "/rest/reservation/form"),
            "event_name": ("PUT", "/rest/reservation/form"),
            "cart_read": ("GET", "/rest/transaction"),
            "cart_summary": ("GET", "/rest/order/summary?from=shoppingcart"),
            "cart_context": ("GET", "/rest/preparation"),
        }
        if op.name == "form":
            import re
            if op.method != "GET" or not re.fullmatch(r"/rest/reservation/form/[1-9][0-9]*", op.path):
                raise BoundaryError("Form read requires an observed positive draft ID")
        elif routes.get(op.name) != (op.method, op.path):
            raise BoundaryError("Unknown operation or method/path mismatch")
        if op.name in ("event_type", "event_name"):
            fields = ({"event_type_id": self.selection.event_type_id, "type": 3} if op.name == "event_type"
                      else {"event_name": self.selection.event_name, "type": 4})
            if self.draft is None or op.body != dict(fields,reno=self.draft.reno,timestamp=self.draft.timestamp):
                raise BoundaryError("Only the exact event-name/type update is allowed; no waiver/custom request")
        if op.name in ("validate", "proceed") and op.body != self._common():
            raise BoundaryError("Selection request differs from exact target")
        if op.name == "patterns":
            expected = dict(resource_id=self.selection.resource_id,
                            datetime_periods=[dict(from_date_time=wire_datetime(self.selection.start),to_date_time=wire_datetime(self.selection.end))],
                            datetime_length=None,reservation_unit=1,customer_id=self.customer_id,
                            company_id=0,attendee=self.selection.attendees)
            if not self.customer_id or op.body != expected:
                raise BoundaryError("Pattern request differs from exact target")
        if op.name == "form_context" and op.body != {"facilityId": self.selection.resource_id}:
            raise BoundaryError("Form-context body differs from observed source call")
        if op.method == "GET" and op.body is not None:
            raise BoundaryError("No hidden data in GET bodies")
        if op.name in EFFECTS and op.effect != EFFECTS[op.name]:
            raise BoundaryError("Cannot downgrade a mutating/unknown operation to a read")
        if op.name not in EFFECTS and op.effect != "read":
            raise BoundaryError("Invalid operation effect")
        write = op.effect != "read"
        if write:
            now, p = self.clock(), self.permission
            self.selection.validate(now)
            if (p is None or p.selection_key != self.selection.key or p.expires.tzinfo is None
                    or now.astimezone(UTC) >= p.expires.astimezone(UTC)
                    or op.name not in p.allowed_operations or not p.approval_reference
                    or p.acknowledges_unknown_hold_or_draft_effects is not True
                    or type(p.customer_id) is not int or p.customer_id != self.customer_id):
                raise BoundaryError("Explicit matching preparation-test approval required")
            if self.checkpoint is None:
                raise BoundaryError("Durable write-ahead checkpoint required")
            if self.ledger.get("uncertain") or self.ledger.get("inflight"):
                raise BoundaryError("Uncertain previous mutation; read-only reconciliation required")
            if self.ledger.get("selection_key", self.selection.key) != self.selection.key:
                raise BoundaryError("Ledger belongs to another date/target")
            if op.name in self.ledger.get("completed_operations", []):
                raise BoundaryError("Operation already completed; reconcile rather than repeat")
            self.ledger.update(selection_key=self.selection.key, inflight=op.name,
                               status="preparation_inflight", deadline=guard_deadline(local_instant(self.selection.start)).isoformat())
            self.checkpoint(copy.deepcopy(self.ledger))
        try:
            body = unwrap(self.transport.request(op.method, op.path, op.body))
        except Exception:
            if write:
                self.ledger.update(uncertain=True, status="reconciliation_required")
                self.checkpoint(copy.deepcopy(self.ledger))
            raise
        if write:
            # Returned body may indicate semantic problems. Do not automatically repeat it.
            self.ledger.update(inflight=None, last_operation=op.name, status="preparation_response_received")
            self.ledger.setdefault("completed_operations", []).append(op.name)
            self.checkpoint(copy.deepcopy(self.ledger))
        return body

    def read_context(self) -> dict:
        self.execute(Operation("logincheck", "GET", "/rest/common/logincheck"))
        mini = self.execute(Operation("mini_cart", "GET", "/rest/reservation/minishoppingcart"))
        if mini.get("booking_count") != 0 or mini.get("resource_count") != 0 or mini.get("permit_number") or mini.get("reno",0)>0:
            raise BoundaryError("Existing mini-cart/draft found; preserve it and reconcile")
        context = self.execute(Operation("form_context", "POST",
                                 f"/rest/reservation/resource/detail/{self.selection.resource_id}/formdata",
                                 {"facilityId": self.selection.resource_id}))
        # createAPI retains original template argument as POST body in the observed old flow.
        family = context.get("data", {}).get("participants", {}).get("family_members", [])
        selected = [p for p in family if p.get("selected")]
        if len(selected) != 1 or not isinstance(selected[0].get("id"), int):
            raise BoundaryError("Resolve the authorized selected customer explicitly")
        self.customer_id = selected[0]["id"]
        return {"selected_customer_id": self.customer_id, "mini_cart_empty": True}

    def _common(self) -> dict:
        if not self.customer_id or not self.group:
            raise BoundaryError("Participant and exact validated selection required")
        checked = exact_group(self.selection, self.group)
        return dict(customer_id=self.customer_id, company_id=0, participant_type=2,
                    reservation_unit="minute", attendee=self.selection.attendees,
                    resource_id=self.selection.resource_id, reservation_time_groups=[checked],
                    reno=0)

    def select_and_validate(self) -> dict:
        if not self.customer_id:
            raise BoundaryError("Read authorized participant context first")
        target = self.selection
        payload = dict(resource_id=target.resource_id,
                       datetime_periods=[dict(from_date_time=wire_datetime(target.start),to_date_time=wire_datetime(target.end))],
                       datetime_length=None, reservation_unit=1,
                       customer_id=self.customer_id,company_id=0,attendee=target.attendees)
        first = self.execute(Operation("patterns", "POST", "/rest/reservation/resource/reservationtimegroup",
                                      payload, EFFECTS["patterns"]))
        try:
            self.group = exact_group(target, first)
        except Exception:
            self._semantic_unknown()
            raise BoundaryError("Selection response was not verified; reconciliation required") from None
        validated = self.execute(Operation("validate", "POST", "/rest/reservation/resource/validation",
                                          self._common(), EFFECTS["validate"]))
        try:
            self.group = exact_group(target, validated)
        except Exception:
            self._semantic_unknown()
            raise BoundaryError("Validation response was not verified; reconciliation required") from None
        return copy.deepcopy(self.group)

    def _semantic_unknown(self):
        self.ledger.update(uncertain=True, status="reconciliation_required")
        if self.checkpoint:
            self.checkpoint(copy.deepcopy(self.ledger))

    def create_draft(self) -> Draft:
        self.execute(Operation("proceed", "POST", "/rest/reservation/resource/proceed", self._common(), EFFECTS["proceed"]))
        try:
            mini = self.execute(Operation("mini_cart", "GET", "/rest/reservation/minishoppingcart"))
        except Exception:
            self._semantic_unknown()
            raise BoundaryError("Draft creation acknowledged but readback failed; no retry") from None
        if (mini.get("booking_count") != 1 or mini.get("resource_count") != 1
                or mini.get("last_proceed_resource_id") != self.selection.resource_id or mini.get("permit_number")):
            self.ledger.update(uncertain=True, status="unexpected_draft_state")
            self.checkpoint(copy.deepcopy(self.ledger))
            raise BoundaryError("Draft readback differs; no retry, deletion or submission")
        try:
            self.draft = self.read_form(mini["reno"])
            verify_form_selection(self.draft,self.selection,self.customer_id)
        except Exception:
            self._semantic_unknown()
            raise BoundaryError("Draft scope could not be verified; no retry") from None
        self.ledger.update(draft_reno=self.draft.reno, status="draft_created")
        self.checkpoint(copy.deepcopy(self.ledger))
        return self.draft

    def read_form(self, reno: int) -> Draft:
        if type(reno) is not int or reno <= 0:
            raise BoundaryError("Use an observed draft ID")
        return parse_form(reno, self.execute(Operation("form", "GET", f"/rest/reservation/form/{reno}")))

    def update_event_type(self) -> Draft:
        return self._update("event_type", 3, {"event_type_id": self.selection.event_type_id})

    def update_event_name(self) -> Draft:
        return self._update("event_name", 4, {"event_name": self.selection.event_name})

    def _update(self, name: str, kind: int, fields: dict) -> Draft:
        if self.draft is None:
            raise BoundaryError("Read form first")
        verify_form_selection(self.draft,self.selection,self.customer_id)
        payload = dict(fields, type=kind, reno=self.draft.reno, timestamp=self.draft.timestamp)
        response = self.execute(Operation(name, "PUT", "/rest/reservation/form", payload, EFFECTS[name]))
        try:
            if response.get("validation_msg") or response.get("errors"):
                raise BoundaryError("Draft validation requires review")
            self.draft = parse_form(self.draft.reno, response)
            verify_form_selection(self.draft,self.selection,self.customer_id)
            field = "event_type" if name == "event_type" else "event_name"
            expected = self.selection.event_type_id if name == "event_type" else self.selection.event_name
            if self.draft.raw["reservation"].get(field) != expected:
                raise BoundaryError("Updated event detail was not verified")
        except Exception:
            self._semantic_unknown()
            raise BoundaryError("Draft update response unverified; no automatic retry") from None
        return self.draft

    def cart_snapshot(self) -> "CartSnapshot":
        transactions = self.execute(Operation("cart_read", "GET", "/rest/transaction"))
        summary = self.execute(Operation("cart_summary", "GET", "/rest/order/summary?from=shoppingcart"))
        return parse_cart(transactions, summary)

    def prepare_cart_context(self) -> dict:
        return self.execute(Operation("cart_context", "GET", "/rest/preparation", effect=EFFECTS["cart_context"]))

    def reserve_request_plan(self) -> Operation:
        if self.draft is None:
            raise BoundaryError("No draft")
        # Useful for later contract observation; execute() always denies this endpoint.
        return Operation("reserve", "POST", f"/rest/reservation/form/reserve/{self.draft.reno}/{self.draft.timestamp}",
                         effect="may add to cart OR submit reservation request; possible CAPTCHA/waivers/hold")


def money(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise BoundaryError("Missing or malformed exact amount") from None
    if not result.is_finite() or result < 0:
        raise BoundaryError("Invalid exact amount")
    return result


@dataclass(frozen=True)
class CartSnapshot:
    items: tuple[dict, ...]
    due_now: Decimal
    currency: str
    checkout_valid: bool
    adjustments: dict
    fingerprint: str
    final_payment_total_verified: bool = False


def parse_cart(transactions: dict, summary_body: dict) -> CartSnapshot:
    summary = summary_body.get("order_summary", {})
    rows = [r for p in transactions.get("participants", []) for r in p.get("transactions", [])]
    if len(rows) != 1 or rows[0].get("transaction_type") not in (16, 91):
        raise BoundaryError("Exactly one reservation transaction required; preserve unrelated cart items")
    row = rows[0]
    if len(row.get("resources", [])) != 1:
        raise BoundaryError("Exactly one court required")
    resource = row["resources"][0]
    bookings = resource.get("booking_details", [])
    if len(bookings) != 1 or row.get("booking_count") != 1 or row.get("resource_count") != 1:
        raise BoundaryError("Exactly one booked interval required")
    booking = bookings[0]
    required = [row.get("reno"), row.get("receipt_entry_identity"), resource.get("resource_id"),
                booking.get("start_datetime"), booking.get("end_datetime"), booking.get("attendee")]
    if any(v is None for v in required) or row.get("online_entry_completed") is not True:
        raise BoundaryError("Incomplete reservation cart or missing identity fields")
    item = dict(reno=row["reno"],receipt_entry_identity=row["receipt_entry_identity"],
                resource_id=resource["resource_id"], start=wire_datetime(booking["start_datetime"]),
                end=wire_datetime(booking["end_datetime"]),attendees=booking["attendee"],
                has_reservation_request=row.get("has_reservation_request"))
    due = money(summary.get("due_now"))
    transaction_due = money(row.get("due_now"))
    if summary.get("cart_count") != 1:
        raise BoundaryError("Summary/transaction count mismatch")
    adjustments = {k:money(summary.get(k,0)) for k in ["sub_total","taxes","processing_fee","processing_fee_discount",
                    "payment_from_account","payment_plan_deferred","gift_card_amount","coupon","subsidy_amount"]}
    item["transaction_due_now"] = str(transaction_due)
    stable = {"item":item,"due_now":str(due),"adjustments":{k:str(v) for k,v in adjustments.items()}}
    fingerprint = hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()
    # Frontend renders USD, but this remains a cart amount, not an asserted final payment-page amount.
    return CartSnapshot((item,),due,"USD",summary.get("checkout_valid") is True,adjustments,fingerprint)


@dataclass(frozen=True)
class BrowserHandoff:
    url: str
    expected_fingerprint: str
    target_key: str
    payment_page_ready: bool
    blocker: str


def handoff(selection: Selection, snapshot: CartSnapshot) -> BrowserHandoff:
    item=snapshot.items[0]
    if (item["resource_id"],item["start"],item["end"],item["attendees"]) != (
            selection.resource_id,wire_datetime(selection.start),wire_datetime(selection.end),selection.attendees):
        raise BoundaryError("Cart does not match the exact preparation target")
    if selection.max_total is not None and snapshot.due_now > selection.max_total:
        raise BoundaryError("Cart amount exceeds explicit per-date cap")
    # No account credits/payment plans/gifts/coupons are assumed to satisfy authorized payment scope.
    if any(snapshot.adjustments[k] for k in ["payment_from_account","payment_plan_deferred","gift_card_amount","coupon","subsidy_amount"]):
        raise BoundaryError("Nonstandard financial adjustments require separate review")
    route="/newcart/checkout" if snapshot.checkout_valid else "/newcart"
    blocker=("Reverify exact payment-page total; payment is user handoff only" if snapshot.checkout_valid else
             "Payment page requires consequential POST /checkout, hard-denied in this prototype")
    return BrowserHandoff(BASE+route,snapshot.fingerprint,selection.key,snapshot.checkout_valid,blocker)


def verify_browser_handoff(plan: BrowserHandoff, browser_snapshot: CartSnapshot, observed_url: str) -> bool:
    # Browser observer must use permitted UI/DOM only. It supplies a fresh independent snapshot.
    expected, actual = urlparse(plan.url), urlparse(observed_url)
    if (actual.scheme,actual.netloc,actual.path) != (expected.scheme,expected.netloc,expected.path):
        raise BoundaryError("Unexpected browser checkout origin/path")
    if actual.query or actual.fragment:
        raise BoundaryError("No sensitive URL token/state handoff is implemented")
    if browser_snapshot.fingerprint != plan.expected_fingerprint:
        raise BoundaryError("Browser account/cart state differs; don't import cookies or resubmit")
    if browser_snapshot.checkout_valid != plan.payment_page_ready:
        raise BoundaryError("Browser checkout eligibility changed; re-read and review")
    return True
