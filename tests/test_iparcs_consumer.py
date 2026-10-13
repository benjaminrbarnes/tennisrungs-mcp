import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from tennisrungs_mcp.iparcs_consumer import (Authorization, BoundaryError, ConsumerAdapter, PublicTransport,
                            covers, guard_deadline, local_instant, permit_state, review_checkout, unwrap)


def envelope(body, code="0000"):
    return {"headers": {"response_code": code}, "body": body}


class Fake:
    def __init__(self, results): self.results, self.calls = iter(results), []
    def request(self, method, path, body=None):
        self.calls.append((method, path, body)); return next(self.results)


def day(slots=None, status=0, d="2030-01-01"):
    return {"date": d, "status": status, "times": slots or [], "check_out_only": False}


def slot(a, b, cross=False, available=True):
    return dict(start_time=a, end_time=b, is_cross_day=cross, available=available)


class Tests(unittest.TestCase):
    def test_whole_block_not_overlap(self):
        value = day([slot("06:00:00", "10:00:00"), slot("12:00:00", "23:00:00")])
        self.assertFalse(covers(value, "09:30:00", "11:30:00"))
        self.assertTrue(covers(value, "08:00:00", "10:00:00"))
        self.assertFalse(covers(value, "08:01:00", "09:00:00"))

    def test_every_closure_and_unknown_status(self):
        for status in [2, 3, 4, 5, 6, 7, 8, 9, 10, 999]:
            self.assertFalse(covers(day([slot("06:00:00", "23:00:00")], status), "09:30:00", "11:30:00"))
        self.assertFalse(covers(day([slot("06:00:00", "23:00:00", available=False)]), "09:30:00", "11:30:00"))

    def test_midnight_anomaly_fails_closed(self):
        with self.assertRaises(BoundaryError):
            covers(day([slot("06:00:00", "00:00:00")]), "09:30:00", "11:30:00")
        with self.assertRaises(BoundaryError):
            covers(day([slot("22:00:00", "02:00:00", True)]), "22:00:00", "23:00:00")

    def test_dst_invalid_and_ambiguous_wall_times(self):
        for value in ["2030-03-10T02:30:00", "2030-11-03T01:30:00"]:
            with self.assertRaises(BoundaryError): local_instant(value)
        self.assertEqual(local_instant("2030-11-03T01:30:00-04:00").utcoffset(), timedelta(hours=-4))

    def test_deadline_uses_elapsed_time_across_dst(self):
        start = local_instant("2030-11-04T09:30:00")
        deadline = guard_deadline(start)
        self.assertEqual((start.astimezone(timezone.utc)-deadline.astimezone(timezone.utc)).total_seconds(), 72*3600+900)
        self.assertEqual(deadline.isoformat(), "2030-11-01T10:15:00-04:00")

    def test_application_error_even_when_http_is_success(self):
        with self.assertRaises(BoundaryError): unwrap(envelope({}, "0002"))
        self.assertEqual(unwrap(envelope({}, "0001")), {})

    def test_cursor_pagination_uses_body_not_envelope(self):
        f = Fake([envelope(dict(items=[{"id":1}],total=2,next_start_index=20,search_client_id="synthetic")),
                  envelope(dict(items=[{"id":2}],total=2,next_start_index=40))])
        self.assertEqual([i["id"] for i in ConsumerAdapter(f).search("synthetic")], [1,2])
        self.assertEqual(f.calls[1][2]["start_index"],20)
        self.assertEqual(f.calls[1][2]["search_client_id"],"synthetic")

    def test_cursor_stall_not_partial_success(self):
        f=Fake([envelope(dict(items=[{"id":1}],total=-1,next_start_index=0))])
        with self.assertRaises(BoundaryError): ConsumerAdapter(f).search("synthetic")

    def test_availability_chunk_ranges_inclusive_no_overlap(self):
        start=date(2030,1,1)
        values=[day(d=(start+timedelta(days=i)).isoformat()) for i in range(43)]
        f=Fake([envelope({"details":{"daily_details":values[:42]}}),envelope({"details":{"daily_details":values[42:]}})])
        self.assertEqual(len(ConsumerAdapter(f).availability(1,start,start+timedelta(days=42))),43)
        self.assertIn("end_date=2030-02-11",f.calls[0][1])
        self.assertIn("start_date=2030-02-12",f.calls[1][1])

    def test_missing_date_is_not_open(self):
        f=Fake([envelope({"details":{"daily_details":[]}})])
        with self.assertRaises(BoundaryError): ConsumerAdapter(f).availability(1,date(2030,1,1),date(2030,1,1))

    def test_public_transport_cannot_write_or_read_credentials(self):
        for method,path in [("POST","/rest/checkout"),("POST","/rest/user/signin"),
                            ("PUT","/rest/reservation/form"),("GET","/rest/system/loginuser")]:
            with self.assertRaises(BoundaryError): PublicTransport().request(method,path)

    def test_paid_tentative_is_not_staff_approved(self):
        value=permit_state("Tentative",Decimal("10"),Decimal("0"))
        self.assertTrue(value["paid"]); self.assertTrue(value["approval_pending"])
        self.assertFalse(value["staff_approved"])

    def test_exact_total_per_date_and_uncertain_attempt(self):
        auth=Authorization("2030-01-05",1,"2030-01-05T09:30:00","2030-01-05T11:30:00",Decimal("15"))
        cart={"items":[dict(date=auth.date,resource_id=1,start=auth.start,end=auth.end)],
              "currency":"USD","financial_obligation_known":True,"all_in_total":"15.00","due_now":"15.00"}
        now=local_instant("2030-01-01T09:00:00")
        review_checkout(auth,cart,{"2030-01-04":{"booking_attempted":True}},now)
        with self.assertRaises(BoundaryError): review_checkout(auth,cart,{auth.date:{"booking_attempted":True}},now)
        cart["all_in_total"]="15.01"
        with self.assertRaises(BoundaryError): review_checkout(auth,cart,{},now)
        cart.update(all_in_total="0",due_now="0",financial_obligation_known=False)
        with self.assertRaises(BoundaryError): review_checkout(auth,cart,{},now)


if __name__ == "__main__": unittest.main()
