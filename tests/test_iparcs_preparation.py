"""Synthetic fixtures only: no real account, permit, credential or payment details."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tennisrungs_mcp.iparcs_consumer import BoundaryError
from tennisrungs_mcp.iparcs_preparation import (BrowserHandoff, Draft, EFFECTS, Operation, PreparationClient, Selection,
                                TestPermission, exact_group, handoff, parse_cart, parse_form,
                                verify_browser_handoff, verify_form_selection, wire_datetime)

NOW=datetime(2030,1,1,12,tzinfo=timezone.utc)


def target(**kw):
    base=dict(resource_id=999,start="2030-01-05T09:30:00",end="2030-01-05T11:30:00")
    base.update(kw); return Selection(**base)


def group(s=None):
    s=s or target()
    return dict(group_id="synthetic-group",availability="Available",summary="synthetic",short_summary="synthetic",
                reservation_times=[dict(start_event_datetime=wire_datetime(s.start),end_event_datetime=wire_datetime(s.end),
                                        availability="Available",booking_identifier="synthetic-server-reference")])


def form(stamp=1,s=None):
    s=s or target()
    return dict(timestamp=stamp,event_fee={},questions={"data":[]},checklists={},
                reservation=dict(customer_id=77,company_id=0,participant_type=2,event_type=27,event_name="Tennis",
                                 resources=[dict(resource_id=s.resource_id,schedules=[dict(
                                     start_event_datetime=wire_datetime(s.start),end_event_datetime=wire_datetime(s.end),
                                     attendance=s.attendees)])]))


def cart(due="10",ready=False):
    s=target()
    transaction=dict(reno=55,receipt_entry_identity="synthetic-entry",transaction_type=16,
                     online_entry_completed=True,resource_count=1,booking_count=1,has_reservation_request=True,
                     due_now=due,resources=[dict(resource_id=999,booking_details=[dict(
                         start_datetime=wire_datetime(s.start),end_datetime=wire_datetime(s.end),attendee=2)])])
    return {"participants":[{"transactions":[transaction]}]}, {"order_summary":dict(cart_count=1,due_now=due,
                sub_total=due,taxes=0,processing_fee=0,checkout_valid=ready)}


class Fake:
    def __init__(self,results=()):self.results=iter(results);self.calls=[]
    def request(self,method,path,body=None):
        self.calls.append((method,path,copy.deepcopy(body)))
        result=next(self.results)
        if isinstance(result,Exception):raise result
        return {"headers":{"response_code":"0000"},"body":copy.deepcopy(result)}


def client(results=(),*,s=None,permit=True,sink=True,ops=None):
    s=s or target();f=Fake(results);checks=[]
    p=TestPermission(s.key,frozenset(ops or EFFECTS),NOW+timedelta(hours=1),"synthetic-test-approval",True,customer_id=77) if permit else None
    c=PreparationClient(f,s,permission=p,clock=lambda:NOW,checkpoint=checks.append if sink else None)
    c.customer_id=77
    return c,f,checks


class Tests(unittest.TestCase):
    def test_no_mutation_permission_defaults(self):
        c,f,_=client(permit=False)
        with self.assertRaises(BoundaryError):c.select_and_validate()
        self.assertEqual(f.calls,[])

    def test_no_mutation_without_durable_checkpoint(self):
        c,f,_=client(sink=False)
        with self.assertRaises(BoundaryError):c.select_and_validate()
        self.assertEqual(f.calls,[])

    def test_permission_is_exact_target_not_old_date_or_cap(self):
        c,f,_=client(s=target(max_total=Decimal("15")))
        c.permission=TestPermission(target().key,frozenset(EFFECTS),NOW+timedelta(hours=1),"synthetic",True)
        with self.assertRaises(BoundaryError):c.select_and_validate()
        self.assertEqual(f.calls,[])

    def test_no_inferred_budget(self):
        self.assertIsNone(target().max_total)
        target().validate(NOW)

    def test_selection_source_contract(self):
        c,f,checks=client([group(),{"reservation_time_groups":[group()]}])
        selected=c.select_and_validate()
        self.assertEqual([x[1] for x in f.calls],["/rest/reservation/resource/reservationtimegroup","/rest/reservation/resource/validation"])
        self.assertEqual(f.calls[0][2]["reservation_unit"],1)
        self.assertEqual(f.calls[1][2]["reservation_unit"],"minute")
        self.assertEqual(selected["reservation_times"][0]["booking_identifier"],"booking_1")
        self.assertEqual(checks[0]["inflight"],"patterns")

    def test_adjusted_partial_or_extra_intervals_rejected(self):
        for field,value in [("availability","Partially Available"),("adjusted_message","changed"),
                            ("reservation_times",group()["reservation_times"]*2)]:
            g=group();g[field]=value
            with self.assertRaises(BoundaryError):exact_group(target(),g)

    def test_server_time_change_rejected(self):
        g=group();g["reservation_times"][0]["end_event_datetime"]="2030-01-05 11:00:00"
        with self.assertRaises(BoundaryError):exact_group(target(),g)

    def test_uncertain_mutation_never_retried(self):
        c,f,checks=client([TimeoutError("synthetic timeout")])
        with self.assertRaises(TimeoutError):c.select_and_validate()
        self.assertTrue(c.ledger["uncertain"])
        with self.assertRaises(BoundaryError):c.select_and_validate()
        self.assertEqual(len(f.calls),1)

    def test_completed_selection_never_replayed(self):
        c,f,_=client([group(),{"reservation_time_groups":[group()]}])
        c.select_and_validate()
        with self.assertRaises(BoundaryError):c.select_and_validate()
        self.assertEqual(len(f.calls),2)

    def test_effect_cannot_be_downgraded(self):
        c,f,_=client()
        with self.assertRaises(BoundaryError):c.execute(Operation("cart_context","GET","/rest/preparation",effect="read"))
        self.assertEqual(f.calls,[])

    def test_irreversible_endpoints_hard_denied_even_with_permission(self):
        c,f,_=client(ops=["reserve","checkout","payment","event_name"])
        for path in ["/rest/checkout","/rest/checkout/order/commit","/rest/reservation/form/reserve/55/1",
                     "/rest/common/signwaivers","/rest/checkout/payment/iframeurl"]:
            with self.assertRaises(BoundaryError):c.execute(Operation("checkout","POST",path,{}))
        self.assertEqual(f.calls,[])

    def test_waiver_or_arbitrary_update_cannot_hide_as_event_name(self):
        c,f,_=client();c.draft=parse_form(55,form())
        with self.assertRaises(BoundaryError):c.execute(Operation("event_name","PUT","/rest/reservation/form",
                                                    {"type":8,"reno":55,"timestamp":1,"event_name":"Tennis"},EFFECTS["event_name"]))
        self.assertEqual(f.calls,[])

    def test_scope_tampering_blocked_before_transport(self):
        c,f,_=client();c.group=exact_group(target(),group())
        b=c._common();b["resource_id"]=888
        with self.assertRaises(BoundaryError):c.execute(Operation("proceed","POST","/rest/reservation/resource/proceed",b,EFFECTS["proceed"]))
        self.assertEqual(f.calls,[])

    def test_draft_chain_and_server_timestamp_updates(self):
        mini=dict(reno=55,booking_count=1,resource_count=1,last_proceed_resource_id=999,permit_number=None)
        c,f,_=client([group(),{"reservation_time_groups":[group()]},{},mini,form(1),form(2),form(3)])
        c.select_and_validate();c.create_draft();c.update_event_type();c.update_event_name()
        self.assertEqual(c.draft.timestamp,3)
        self.assertEqual(f.calls[-1][2],dict(event_name="Tennis",type=4,reno=55,timestamp=2))

    def test_form_readback_binds_scope(self):
        d=parse_form(55,form());verify_form_selection(d,target(),77)
        d.raw["reservation"]["resources"][0]["schedules"][0]["attendance"]=3
        with self.assertRaises(BoundaryError):verify_form_selection(d,target(),77)

    def test_existing_mini_cart_preserved(self):
        c,f,_=client([{},dict(reno=55,booking_count=1,resource_count=1)])
        with self.assertRaises(BoundaryError):c.read_context()
        self.assertEqual(len(f.calls),2)

    def test_cart_exact_due_with_processing_fee_not_estimated(self):
        t,b=cart();b["order_summary"].update(processing_fee="1.25",due_now="11.25")
        snap=parse_cart(t,b)
        self.assertEqual(snap.due_now,Decimal("11.25"))
        self.assertEqual(snap.items[0]["transaction_due_now"],"10")
        self.assertFalse(snap.final_payment_total_verified)

    def test_unrelated_cart_items_block_handoff(self):
        t,b=cart();t["participants"][0]["transactions"].append(copy.deepcopy(t["participants"][0]["transactions"][0]))
        with self.assertRaises(BoundaryError):parse_cart(t,b)

    def test_zero_due_still_stops_before_checkout(self):
        t,b=cart("0");snap=parse_cart(t,b);h=handoff(target(),snap)
        self.assertTrue(h.url.endswith("/newcart"));self.assertFalse(h.payment_page_ready)
        self.assertIn("hard-denied",h.blocker)

    def test_handoff_requires_same_browser_cart(self):
        t,b=cart(ready=True);snap=parse_cart(t,b);h=handoff(target(),snap)
        self.assertTrue(verify_browser_handoff(h,snap,h.url))
        t2,b2=cart("11",ready=True)
        with self.assertRaises(BoundaryError):verify_browser_handoff(h,parse_cart(t2,b2),h.url)
        with self.assertRaises(BoundaryError):verify_browser_handoff(h,snap,"https://example.invalid/newcart/checkout")
        t3,b3=cart(ready=False)
        with self.assertRaises(BoundaryError):verify_browser_handoff(h,parse_cart(t3,b3),h.url)

    def test_per_date_cap_and_adjustments(self):
        t,b=cart();snap=parse_cart(t,b)
        with self.assertRaises(BoundaryError):handoff(target(max_total=Decimal("9.99")),snap)
        b["order_summary"]["payment_plan_deferred"]="1"
        with self.assertRaises(BoundaryError):handoff(target(),parse_cart(t,b))

    def test_no_erasing_dst_fold_into_wire_format(self):
        with self.assertRaises(BoundaryError):wire_datetime("2030-11-03T01:30:00-04:00")


if __name__ == "__main__":unittest.main()
