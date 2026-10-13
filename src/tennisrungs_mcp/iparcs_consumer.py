"""Consumer iParcs read-only prototype. No cookies, login, write executor or secrets.

Contracts observed 2026-10-13 in separate read-only research; see docs/iparcs-evidence.md.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

BASE = "https://anc.apm.activecommunities.com/atlantadprca"
ATLANTA = ZoneInfo("America/New_York")
UTC = timezone.utc
COURTS = {1: 7245, 2: 7246, 3: 7247, 4: 7248}
AUTH_CODES = {"0002", "0006", "0007", "0009", "0010", "0011", "0012", "0021"}


from .models import IntegrationError


class BoundaryError(IntegrationError):
    pass


def unwrap(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("headers"), dict):
        raise BoundaryError("Consumer envelope schema changed")
    code = raw.get("headers", {}).get("response_code")
    if not isinstance(code, str) or not re.fullmatch(r"\d{4}", code):
        raise BoundaryError("Consumer result-code schema changed")
    if code in AUTH_CODES:
        raise BoundaryError(f"Session/security boundary ({code}); renew via approved browser flow")
    if code not in {"0000", "0001"}:
        # Do not log the response body, which can contain personal information.
        raise BoundaryError(f"Consumer application result {code or 'missing'}")
    if not isinstance(raw.get("body"), dict):
        raise BoundaryError("Consumer response body schema changed")
    return raw["body"]


class Transport(Protocol):
    def request(self, method: str, path: str, body: dict | None = None) -> dict: ...


class PublicTransport:
    """Credential-free allowlist. Only the observed search POST is permitted."""

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        bare = path.split("?", 1)[0]
        allowed_get = (
            bare == "/rest/reservation/resource/searchoptions"
            or re.fullmatch(r"/rest/reservation/resource/detail/[0-9]+", bare)
            or re.fullmatch(r"/rest/reservation/resource/availability/daily/[0-9]+", bare)
        )
        if not ((method == "GET" and allowed_get and body is None)
                or (method == "POST" and bare == "/rest/reservation/resource")):
            raise BoundaryError("Endpoint not in public read-only allowlist")
        headers = {
            "Content-Type": "application/json" if method == "POST" else "application/x-www-form-urlencoded;charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "page_info": json.dumps({"page_number": 1, "total_records_per_page": 20}),
        }
        req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method=method)
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        # No cookies, login, cross-origin redirect, challenge handling or retry.
        try:
            with build_opener(NoRedirect()).open(req, timeout=30) as response:
                if response.headers.get_content_type() != "application/json":
                    raise BoundaryError("Expected consumer JSON; stop for browser/security review")
                result = json.load(response)
                if not isinstance(result, dict):
                    raise BoundaryError("Unexpected consumer envelope shape")
                return result
        except HTTPError as e:
            raise BoundaryError(f"Consumer HTTP {e.code}; stop without retry or alternate route") from None
        except (URLError, ValueError, TimeoutError):
            raise BoundaryError("Consumer read failed; response details suppressed") from None


def search_body(name: str, start_index: int = 0, search_client_id: str = "") -> dict:
    return dict(name=name, attendee=0, date_times=[], facility_type_ids=[],
                event_type_ids=[], reservation_group_ids=[], amenity_ids=[],
                facility_id=0, equipment_id=0, center_id=0, resource_type=-1,
                client_coordinate="", order_by_field="name", order_direction="asc",
                page_size=20, start_index=start_index, search_client_id=search_client_id,
                date_time_length=None)


class ConsumerAdapter:
    def __init__(self, transport: Transport | None = None):
        self.transport = transport or PublicTransport()

    def search(self, name: str, max_pages: int = 100) -> list[dict]:
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise BoundaryError("A bounded explicit facility keyword is required")
        if not isinstance(max_pages, int) or not 1 <= max_pages <= 100:
            raise BoundaryError("Invalid search page bound")
        index, cursor, seen = 0, "", {}
        for _ in range(max_pages):
            body = unwrap(self.transport.request("POST", "/rest/reservation/resource?locale=en-US",
                                                 search_body(name, index, cursor)))
            if body.get("too_many_resources"):
                raise BoundaryError("Search needs narrower filters")
            items = body.get("items", [])
            if not isinstance(items, list):
                raise BoundaryError("Search item schema changed")
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), int) or isinstance(item.get("id"), bool):
                    raise BoundaryError("Search resource identity schema changed")
                seen[item["id"]] = item
            total = body.get("total", -1)
            if not isinstance(total, int) or isinstance(total, bool):
                raise BoundaryError("Search total schema changed")
            if total >= 0 and len(seen) == total:
                return list(seen.values())
            if total >= 0 and len(seen) > total:
                raise BoundaryError("Search result count exceeds reported total")
            if not items:
                raise BoundaryError("Search ended before total coverage was established")
            nxt = body.get("next_start_index")
            if not isinstance(nxt, int) or nxt <= index:
                raise BoundaryError("Search cursor did not advance; results incomplete")
            index, cursor = nxt, body.get("search_client_id", cursor)
        raise BoundaryError("Search pagination bound reached; results incomplete")

    def detail(self, resource_id: int) -> dict:
        validate_resource_id(resource_id)
        body = unwrap(self.transport.request("GET", f"/rest/reservation/resource/detail/{int(resource_id)}"))
        if not isinstance(body.get("resource_detail"), dict):
            raise BoundaryError("Resource detail unavailable or schema changed")
        return body

    def availability(self, resource_id: int, start: date, end: date) -> list[dict]:
        validate_resource_id(resource_id)
        if end < start:
            raise ValueError("end before start")
        if (end - start).days > 365:
            raise BoundaryError("Availability read exceeds one-year bound")
        days, cursor = {}, start
        # The observed calendar uses inclusive six-week ranges. Chunk without overlap.
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=41), end)
            query = urlencode(dict(start_date=cursor.isoformat(), end_date=chunk_end.isoformat(),
                                   customer_id=0, company_id=0, locale="en-US"))
            raw = self.transport.request("GET", f"/rest/reservation/resource/availability/daily/{int(resource_id)}?{query}")
            details = unwrap(raw).get("details")
            if not isinstance(details, dict) or not isinstance(details.get("daily_details"), list):
                raise BoundaryError("Daily calendar schema changed")
            if "resource_id" in details and details["resource_id"] != resource_id:
                raise BoundaryError("Availability response resource differs from requested court")
            returned = details["daily_details"]
            chunk = {}
            for item in returned:
                try:
                    key = date.fromisoformat(item["date"])
                except (KeyError, TypeError, ValueError):
                    raise BoundaryError("Calendar day schema changed") from None
                if key in chunk or not cursor <= key <= chunk_end:
                    raise BoundaryError("Duplicate or out-of-range calendar day")
                chunk[key] = item
            expected = {cursor + timedelta(days=i) for i in range((chunk_end-cursor).days+1)}
            if set(chunk) != expected:
                raise BoundaryError("Calendar response incomplete; cannot infer missing days are open")
            # Wrapper page_info was inconsistent in the live response. Coverage is authoritative.
            days.update(chunk)
            cursor = chunk_end + timedelta(days=1)
        return [days[d] for d in sorted(days)]


def validate_resource_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BoundaryError("Resource IDs must be positive integers")


def local_instant(value: str) -> datetime:
    """Parse agency wall time; reject ambiguous/nonexistent DST instants."""
    naive = datetime.fromisoformat(value)
    if naive.tzinfo is not None:
        return naive.astimezone(ATLANTA)
    choices = set()
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=ATLANTA, fold=fold).astimezone(UTC)
        if candidate.astimezone(ATLANTA).replace(tzinfo=None) == naive:
            choices.add(candidate)
    if len(choices) != 1:
        raise BoundaryError("Ambiguous or nonexistent Atlanta wall time; explicit offset required")
    return choices.pop().astimezone(ATLANTA)


def guard_deadline(start: datetime) -> datetime:
    if start.tzinfo is None:
        raise ValueError("Timezone required")
    # Rolling 72 elapsed hours plus a conservative 15-minute guard, including DST.
    return (start.astimezone(UTC) - timedelta(hours=72, minutes=15)).astimezone(ATLANTA)


def covers(day: dict, start: str, end: str) -> bool:
    """Whole-block containment; never combine separated openings across a gap.

    Same-day tennis only. Unknown statuses and inconsistent midnight responses fail closed.
    """
    s, e = local_instant(day["date"] + "T" + start), local_instant(day["date"] + "T" + end)
    if e.astimezone(UTC) <= s.astimezone(UTC):
        raise BoundaryError("Cross-date bookings require explicit reviewed dates")
    if s.date().isoformat() != day["date"] or e.date().isoformat() != day["date"]:
        raise BoundaryError("Requested offset shifts outside the reviewed Atlanta day")
    if s.minute % 5 or e.minute % 5 or s.second or e.second or s.microsecond or e.microsecond:
        return False
    if isinstance(day.get("status"), bool) or day.get("status") not in (0, 1) or day.get("check_out_only") or day.get("check_in_only"):
        return False
    for slot in day.get("times", []):
        if slot.get("available") is not True:
            continue
        a = local_instant(day["date"] + "T" + slot["start_time"])
        b = local_instant(day["date"] + "T" + slot["end_time"])
        if b.astimezone(UTC) <= a.astimezone(UTC) and not slot.get("is_cross_day"):
            raise BoundaryError("Calendar midnight/cross-day inconsistency; site validation required")
        if slot.get("is_cross_day"):
            raise BoundaryError("Cross-day availability requires reviewed normalization")
        if a.astimezone(UTC) <= s.astimezone(UTC) and e.astimezone(UTC) <= b.astimezone(UTC):
            return True
    return False


@dataclass(frozen=True)
class Authorization:
    date: str
    resource_id: int
    start: str
    end: str
    max_total: Decimal


def review_checkout(auth: Authorization, cart: dict, ledger: dict, now: datetime) -> None:
    """Pure local gate, not a submission function. cart is an adapter-normalized schema."""
    key = auth.date
    if ledger.get(key, {}).get("booking_attempted") or ledger.get(key, {}).get("permit_id"):
        raise BoundaryError("Prior attempt/permit: reconcile history before any new submission")
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    if now.astimezone(UTC) >= guard_deadline(local_instant(auth.start)).astimezone(UTC):
        raise BoundaryError("Conservative booking deadline reached")
    lines = cart.get("items", [])
    if len(lines) != 1:
        raise BoundaryError("Standalone exact reservation cart required")
    line = lines[0]
    if (line.get("date"), line.get("resource_id"), line.get("start"), line.get("end")) != (
            auth.date, auth.resource_id, auth.start, auth.end):
        raise BoundaryError("Cart scope differs from per-date authorization")
    if local_instant(auth.start).date().isoformat() != auth.date:
        raise BoundaryError("Authorization date mismatch")
    if local_instant(auth.end).astimezone(UTC) <= local_instant(auth.start).astimezone(UTC):
        raise BoundaryError("Invalid reservation range")
    if cart.get("currency") != "USD" or cart.get("financial_obligation_known") is not True:
        raise BoundaryError("Exact full financial obligation must be known")
    try:
        total, due = Decimal(str(cart["all_in_total"])), Decimal(str(cart["due_now"]))
    except (KeyError, ArithmeticError):
        raise BoundaryError("Exact checkout amount missing") from None
    if not auth.max_total.is_finite() or auth.max_total < 0:
        raise BoundaryError("Invalid per-date spending cap")
    if not total.is_finite() or not due.is_finite() or total < 0 or due < 0 or due > total or total > auth.max_total:
        raise BoundaryError("Checkout exceeds cap or amount is invalid")


def permit_state(status: str, paid: Decimal, balance: Decimal) -> dict:
    return {"raw_status": status, "paid": paid > 0, "balance_zero": balance == 0,
            "staff_approved": status.casefold() == "approved",
            "approval_pending": status.casefold() == "tentative"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    s = sub.add_parser("search"); s.add_argument("keyword")
    d = sub.add_parser("detail"); d.add_argument("resource_id", type=int)
    a = sub.add_parser("availability"); a.add_argument("resource_id", type=int)
    a.add_argument("start_date"); a.add_argument("end_date")
    args = parser.parse_args(); client = ConsumerAdapter()
    if args.action == "search":
        result = client.search(args.keyword)
    elif args.action == "detail":
        result = client.detail(args.resource_id)
    else:
        result = client.availability(args.resource_id, date.fromisoformat(args.start_date), date.fromisoformat(args.end_date))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
