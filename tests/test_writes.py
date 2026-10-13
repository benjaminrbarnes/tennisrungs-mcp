from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest

from tennisrungs_mcp.client import Client, validate_score_string
from tennisrungs_mcp.journal import Journal
from tennisrungs_mcp.models import ProposalInput, SafetyError, ScoreInput, UnknownOutcome
from tennisrungs_mcp.transport import Transport
from fixtures import dashboard, FORM, RANKINGS, SCORE
from test_transport import COOKIE

P = ProposalInput(201, 101, 401, "2099-10-20", 10, 0, "AM", "Demo Court; 10-noon, reservation pending", True)


def client(tmp_path, handler):
    t = Transport(COOKIE, httpx.Client(transport=httpx.MockTransport(handler)))
    return Client(t, Journal(tmp_path / "ledger.sqlite3"), writes_enabled=True)


def test_journal_is_durable_private_and_deduplicates_changed_notes(tmp_path):
    j = Journal(tmp_path / "ops.sqlite3")
    j.begin("one", "propose", P)
    j.close()
    other = Journal(tmp_path / "ops.sqlite3")
    assert other.get("one")["state"] == "ATTEMPTED"
    with pytest.raises(SafetyError):
        other.begin("different-key", "propose", replace(P, preferred_location="changed"))
    assert (tmp_path / "ops.sqlite3").stat().st_mode & 0o777 == 0o600
    assert b"reservation pending" not in (tmp_path / "ops.sqlite3").read_bytes()


def test_disabled_writes_never_touch_transport(tmp_path):
    c = Client(None)
    with pytest.raises(SafetyError):
        c.propose_match(P, "one", confirmed=True)


def test_autonomous_withdrawal_always_refused_without_request(tmp_path):
    c = client(tmp_path, lambda r: pytest.fail("must not request"))
    with pytest.raises(SafetyError, match="race"):
        c.withdraw_proposal(303, "one", confirmed=True)


def test_proposal_contract_query_checkbox_token_and_verified_id(tmp_path):
    posted = []
    def handler(r):
        if r.method == "POST":
            assert c.journal.get("one")["state"] == "ATTEMPTED"
            posted.append(r)
            return httpx.Response(200, json={"Message": "Proposal Successfully Posted!"})
        if r.url.path == "/Player":
            return httpx.Response(200, text=dashboard(own=bool(posted)))
        return httpx.Response(200, text=FORM if "ProposeMatch" in r.url.path else RANKINGS)
    c = client(tmp_path, handler)
    result = c.propose_match(P, "one", confirmed=True)
    assert result.state == "VERIFIED" and result.challenge_id == 303
    query = parse_qs(posted[0].url.query.decode())
    assert query["TeamId"] == ["201"] and query["ShowMyEmail"] == ["true", "false"]
    assert query["__RequestVerificationToken"] == ["synthetic-test-only"]
    assert posted[0].content == b""
    with pytest.raises(SafetyError):
        c.propose_match(P, "two", confirmed=True)
    assert len(posted) == 1


def test_proposal_wrong_season_team_never_posts(tmp_path):
    def handler(r):
        assert r.method == "GET"
        return httpx.Response(200, text=dashboard() if r.url.path == "/Player" else RANKINGS)
    with pytest.raises(SafetyError, match="team"):
        client(tmp_path, handler).prepare_proposal(replace(P, team_id=999))


def test_uncertain_post_cannot_be_retried_even_with_new_key(tmp_path):
    count = []
    def handler(r):
        if r.method == "POST":
            count.append(r)
            raise httpx.ReadTimeout("private context", request=r)
        return httpx.Response(200, text=dashboard(own=False) if r.url.path == "/Player" else FORM if "ProposeMatch" in r.url.path else RANKINGS)
    c = client(tmp_path, handler)
    with pytest.raises(UnknownOutcome):
        c.propose_match(P, "one", confirmed=True)
    assert c.journal.get("one")["state"] == "UNKNOWN"
    with pytest.raises(SafetyError):
        c.propose_match(P, "two", confirmed=True)
    assert len(count) == 1


def test_manual_withdraw_refuses_accepted_match(tmp_path):
    c = client(tmp_path, lambda r: httpx.Response(200, text=dashboard(status="ACCEPTED")))
    with pytest.raises(SafetyError, match="PROPOSED"):
        c.withdraw_proposal(303, "one", confirmed=True, autonomous=False)


def test_manual_withdraw_readback_failure_is_unknown(tmp_path):
    calls = []
    def handler(r):
        calls.append(r.method)
        if r.method == "POST":
            return httpx.Response(200, json={"Success": True})
        if "POST" in calls:
            raise httpx.ReadTimeout("private", request=r)
        return httpx.Response(200, text=dashboard())
    c = client(tmp_path, handler)
    with pytest.raises(UnknownOutcome):
        c.withdraw_proposal(303, "one", confirmed=True, autonomous=False)
    assert c.journal.get("one")["state"] == "UNKNOWN"


def test_accept_exact_proposal_and_verified_result(tmp_path):
    posted = []
    def handler(r):
        if r.method == "POST":
            posted.append(r)
            return httpx.Response(200, json={"Success": True})
        if "Rankings" in r.url.path:
            return httpx.Response(200, text=RANKINGS)
        return httpx.Response(200, text=dashboard(status="ACCEPTED", own=bool(posted)))
    c = client(tmp_path, handler)
    assert c.accept_proposal(303, 101, 201, "one", confirmed=True).state == "VERIFIED"
    assert parse_qs(posted[0].url.query.decode()) == {"cId": ["303"], "acceptedBy": ["201"]}


def test_score_contract_and_acknowledgment_not_verified(tmp_path):
    posted = []
    def handler(r):
        if r.method == "POST":
            posted.append(r)
            return httpx.Response(200, json={"ErrorsOccurred": False, "Messages": []})
        return httpx.Response(200, text=SCORE if "SubmitChallengeResult" in r.url.path else dashboard(status="ACCEPTED"))
    c = client(tmp_path, handler)
    result = c.report_score(ScoreInput(303, 101, 201, "6-4, 7-5"), "one", confirmed=True)
    assert result.state == "ACKNOWLEDGED"
    assert parse_qs(posted[0].content.decode()) == {"score": ["6-4, 7-5"], "challengeid": ["303"], "matchOutcome": ["PlayedThrough"], "winnerId": ["201"]}


def test_proposal_other_venue_readback_is_unknown(tmp_path):
    posted = []
    def handler(r):
        if r.method == "POST":
            posted.append(r)
            return httpx.Response(200, json={"Success": True})
        if r.url.path == "/Player":
            h = dashboard(own=bool(posted))
            return httpx.Response(200, text=h.replace("Location: Demo Court", "Location: Other Court"))
        return httpx.Response(200, text=FORM if "ProposeMatch" in r.url.path else RANKINGS)
    c = client(tmp_path, handler)
    with pytest.raises(UnknownOutcome):
        c.propose_match(P, "one", confirmed=True)
    assert c.journal.get("one")["state"] == "UNKNOWN"


def test_accept_wrong_authenticated_season_team_never_posts(tmp_path):
    def handler(r):
        assert r.method == "GET"
        return httpx.Response(200, text=RANKINGS.replace("ShowProposeMatch(201", "ShowProposeMatch(999") if "Rankings" in r.url.path else dashboard())
    with pytest.raises(SafetyError, match="season"):
        client(tmp_path, handler).accept_proposal(303, 101, 201, "one", confirmed=True)


@pytest.mark.parametrize("score", ["---", "0-0, 0-0", "4-6, 5-7", "7-6 (8-10), 6-4", "6-4,,6-2"])
def test_invalid_completed_scores_rejected(score):
    with pytest.raises(SafetyError):
        validate_score_string(score, "PlayedThrough")


def test_valid_match_tiebreak_and_incident_scores():
    validate_score_string("6-4,4-6,(10-8)", "PlayedThrough")
    validate_score_string("0-0,0-0", "NoShow")
    validate_score_string("-", "Forfeit")
