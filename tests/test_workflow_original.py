import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from tennisrungs_mcp.workflow import Intent, Observation, reconcile, cutoffs


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2030, 6, 8, 10, tzinfo=ZoneInfo("America/New_York"))
        self.intent = Intent("synthetic-date", self.start, self.start + timedelta(hours=2),
                             "synthetic-court", cap_cents=1500, can_book=True)
        self.now = self.start - timedelta(days=5)
        self.obs = Observation(fresh=True, complete=True, exact_match=True,
                               match_state="ACCEPTED", proposal_id="synthetic-proposal")

    def action(self, i=None, o=None, now=None):
        return reconcile(i or self.intent, o or self.obs, now or self.now).action

    def quote(self, **kwargs):
        base = replace(self.obs, booking_state="QUOTED", checkout_cents=1000,
                       obligation_known=True, checkout_exact=True, cart_isolated=True,
                       payment_verified=True)
        return replace(base, **kwargs)

    def paid(self, **kwargs):
        return replace(self.obs, booking_state="PAID_TENTATIVE", permit_id="synthetic-permit", **kwargs)

    def test_prepare_only_after_acceptance(self):
        self.assertEqual(self.action(), "STAGE_BROWSER_BOOKING")
        self.assertEqual(self.action(o=replace(self.obs, match_state="PROPOSED")), "WAIT")

    def test_no_imported_authority(self):
        self.assertEqual(self.action(i=replace(self.intent, can_book=False)), "REVIEW_BOOKING")
        self.assertEqual(self.action(i=replace(self.intent, cap_cents=None)), "REVIEW_BOOKING")

    def test_per_date_budget_no_pooling(self):
        self.assertEqual(self.action(o=self.quote(checkout_cents=1501)), "BLOCK")
        self.assertEqual(self.action(o=self.quote(checkout_cents=1500)), "BOOKING_COMMIT_READY")

    def test_checkout_all_conditions_required(self):
        for name in ("obligation_known", "checkout_exact", "cart_isolated", "payment_verified"):
            with self.subTest(name=name):
                self.assertEqual(self.action(o=self.quote(**{name: False})), "BLOCK")

    def test_unknown_write_never_retries(self):
        self.assertEqual(self.action(o=replace(self.obs, unknown_write="booking")), "RECONCILE_UNKNOWN")

    def test_incomplete_or_stale_requires_refresh(self):
        self.assertEqual(self.action(o=replace(self.obs, fresh=False)), "REFRESH")
        self.assertEqual(self.action(o=replace(self.obs, complete=False)), "REFRESH")

    def test_exact_scope_required(self):
        self.assertEqual(self.action(o=replace(self.obs, exact_match=False)), "BLOCK")

    def test_withdrawal_race_requires_atomic_capability(self):
        i = replace(self.intent, can_withdraw=True)
        o = replace(self.obs, match_state="PROPOSED")
        guard, _ = cutoffs(self.start)
        self.assertEqual(self.action(i, o, guard), "REVIEW_WITHDRAWAL")
        self.assertEqual(self.action(i, replace(o, withdrawal_atomic=True), guard), "REVIEW_WITHDRAWAL")

    def test_accepted_at_deadline_never_withdraws(self):
        guard, hard = cutoffs(self.start)
        self.assertEqual(self.action(now=guard), "REVIEW_BOOKING")
        self.assertEqual(self.action(now=hard), "BLOCK")

    def test_elapsed_72_hours_across_dst(self):
        start = datetime(2030, 11, 4, 10, tzinfo=ZoneInfo("America/New_York"))
        guard, hard = cutoffs(start)
        self.assertEqual(start.astimezone(timezone.utc) - hard, timedelta(hours=72))
        self.assertEqual(hard - guard, timedelta(minutes=15))

    def test_tentative_never_reopens_checkout(self):
        self.assertEqual(self.action(o=self.paid()), "CHECK_APPROVAL_AT_DUE_TIME")
        self.assertEqual(self.action(o=replace(self.paid(), booking_state="APPROVED")), "STOP")

    def test_calendar_requires_pinned_identity(self):
        i = replace(self.intent, can_calendar=True)
        self.assertEqual(self.action(i, self.paid()), "BLOCK")
        self.assertEqual(self.action(replace(i, calendar_id="synthetic-calendar"), self.paid()), "RECONCILE_CALENDAR")

    def test_message_recipient_and_content(self):
        i = replace(self.intent, can_message=True, recipient_ref="recipient-A", approved_text_hash="hash-A")
        o = self.paid(recipient_verified=True, recipient_ref="recipient-A", text_hash="hash-A")
        self.assertEqual(self.action(i, o), "MESSAGE_COMMIT_READY")
        self.assertEqual(self.action(i, replace(o, recipient_ref="recipient-B")), "BLOCK")
        self.assertEqual(self.action(i, replace(o, text_hash="hash-B")), "BLOCK")
        self.assertEqual(self.action(i, replace(o, message_state="UNKNOWN")), "RECONCILE_MESSAGE")

    def test_no_message_authority_means_no_send(self):
        self.assertEqual(self.action(o=self.paid()), "CHECK_APPROVAL_AT_DUE_TIME")

    def test_boolean_is_not_money(self):
        self.assertEqual(self.action(o=self.quote(checkout_cents=True)), "BLOCK")
        with self.assertRaises(ValueError):
            self.action(i=replace(self.intent, cap_cents=True))

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            cutoffs(self.start.replace(tzinfo=None))


if __name__ == "__main__":
    unittest.main()
