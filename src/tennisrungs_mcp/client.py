import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from . import parsers
from .models import (AuthenticationRequired, ProposalInput, ReadResult, SafetyError,
                     ScoreInput, UnknownOutcome, WriteResult, UnsupportedContract)
from .transport import BASE, parse_write_response


def positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SafetyError("IDs must be positive integers")
    return value


class Client:
    def __init__(self, transport, journal=None, *, writes_enabled=False):
        self.transport = transport
        self.journal = journal
        self.writes_enabled = writes_enabled

    def result(self, path, html, rows, label=None):
        complete, warnings = parsers.coverage(html, rows, label)
        return ReadResult(BASE + path, datetime.now(timezone.utc).isoformat(), rows, complete, warnings)

    def list_current_ladders(self):
        path = "/Player"
        html = self.transport.get(path, private=True)
        return self.result(path, html, parsers.current_ladders(html))

    def list_own_matches(self):
        path = "/Player"
        html = self.transport.get(path, private=True)
        return self.result(path, html, parsers.my_matches(html), "My Challenges")

    def list_own_proposals(self):
        r = self.list_own_matches()
        return ReadResult(r.source_url, r.observed_at,
                          [m for m in r.rows if m.status == "PROPOSED"], r.complete, r.warnings)

    def list_open_proposals(self):
        path = "/Player"
        html = self.transport.get(path, private=True)
        return self.result(path, html, parsers.open_proposals(html), "Open Proposals")

    def get_rankings(self, ladder_id):
        # /Ladders/Rankings is authenticated. Public slug variants are not guessed.
        path = f"/Ladders/Rankings/{positive(ladder_id)}"
        html = self.transport.get(path, private=True)
        return self.result(path, html, parsers.rankings(html))

    def get_player_history(self, team_id):
        path = f"/Public/PlayerMatches?teamId={positive(team_id)}"
        html = self.transport.get(path)
        return self.result(path, html, parsers.history(html))

    def prepare_proposal(self, p: ProposalInput):
        for value in [p.team_id, p.ladder_id, p.location_id]:
            positive(value)
        if not isinstance(p.show_email, bool):
            raise SafetyError("show_email must be boolean")
        day = date.fromisoformat(p.match_date)
        if day < datetime.now(ZoneInfo("America/New_York")).date() or p.minute not in [0, 15, 30, 45] or not 1 <= p.hour <= 12 or p.am_or_pm not in ["AM", "PM"]:
            raise SafetyError("Invalid proposal date/time")
        if not p.preferred_location.strip() or len(p.preferred_location) > 1000:
            raise SafetyError("A bounded explicit location note is required")
        if p.ladder_id not in {l.ladder_id for l in self.list_current_ladders().rows}:
            raise SafetyError("Current ladder membership not established")
        ranking = self.transport.get(f"/Ladders/Rankings/{p.ladder_id}", private=True)
        ids = re.findall(r"tr\.ShowProposeMatch\((\d+)", ranking)
        if ids != [str(p.team_id)]:
            raise SafetyError("Season team does not match authenticated proposal identity")
        html = self.transport.get(f"/Player/ProposeMatch/{p.team_id}", private=True)
        defaults, options = parsers.proposal_form(html)
        hidden_team = next((v for n, v in defaults if n == "TeamId"), None)
        if hidden_team != str(p.team_id) or str(p.location_id) not in options.get("Location", set()):
            raise SafetyError("Live team or venue does not match requested proposal")
        # Preserve anti-forgery fields if the form begins supplying them. Never print them.
        fields = [(n, v) for n, v in defaults if n not in ["TeamId", "ShowMyEmail"]]
        fields += [("TeamId", str(p.team_id)), ("Location", str(p.location_id)),
                   ("MatchDate", day.strftime("%m/%d/%Y")),
                   ("PreferredLocation", p.preferred_location), ("Hour", str(p.hour)),
                   ("Minute", f"{p.minute:02d}"), ("AmOrPm", p.am_or_pm)]
        if p.show_email:
            fields.append(("ShowMyEmail", "true"))
        fields.append(("ShowMyEmail", "false"))
        return fields

    def assert_write(self, confirmed):
        if not self.writes_enabled or not confirmed:
            raise SafetyError("Explicit server write enablement and per-action confirmation required")
        if self.journal is None:
            raise SafetyError("Persistent operation journal required for writes")

    def execute(self, kind, key, payload, path, *, data=None, params=None):
        self.journal.begin(key, kind, payload)
        try:
            raw = self.transport.post(path, data=data, params=params)
            ok = parse_write_response(raw)
            if not ok:
                self.journal.finish(key, "REJECTED")
                return WriteResult(key, "REJECTED", message="Site explicitly rejected request; no retry")
            self.journal.finish(key, "ACKNOWLEDGED")
            return WriteResult(key, "ACKNOWLEDGED", message="Site acknowledged; live read-back still required")
        except Exception:
            self.journal.finish(key, "UNKNOWN")
            raise UnknownOutcome("Submission outcome unknown; reconcile operation before any retry") from None

    def propose_match(self, p: ProposalInput, operation_key, *, confirmed=False):
        self.assert_write(confirmed)
        fields = self.prepare_proposal(p)
        before = self.list_own_matches()
        if not before.complete or any(m.challenge_id is None or m.status == "UNKNOWN" for m in before.rows):
            raise SafetyError("Own match coverage/identity incomplete")
        # Conservative duplicate test: same date/time or an unparseable own proposal blocks.
        desired = self.proposal_time(p)
        for m in before.rows:
            if m.status == "PROPOSED" and m.scheduled_text is None:
                raise SafetyError("Unscheduled own proposal exists; manual duplicate review needed")
            if m.scheduled_text and self.site_time(m.scheduled_text) == desired:
                raise SafetyError("Own match already exists at requested date/time")
        result = self.execute("propose", operation_key, p, "/Player/ProposeMatch", params=fields)
        if result.state == "REJECTED":
            return result
        try:
            after = self.list_own_matches()
            new = [m for m in after.rows if m.challenge_id not in {x.challenge_id for x in before.rows}
                   and m.status in ["PROPOSED", "ACCEPTED"] and m.scheduled_text
                   and self.site_time(m.scheduled_text) == desired and m.ladder_name in
                   {l.name for l in self.list_current_ladders().rows if l.ladder_id == p.ladder_id}]
            if not after.complete or len(new) != 1:
                raise UnknownOutcome("Proposal identity could not be reconciled")
            self.journal.finish(operation_key, "VERIFIED", new[0].challenge_id)
            return WriteResult(operation_key, "VERIFIED", new[0].challenge_id)
        except Exception:
            self.journal.finish(operation_key, "UNKNOWN")
            raise UnknownOutcome("Proposal acknowledged but read-back uncertain; do not repost") from None

    def withdraw_proposal(self, challenge_id, operation_key, *, confirmed=False, autonomous=True):
        self.assert_write(confirmed)
        positive(challenge_id)
        if autonomous:
            raise SafetyError("Autonomous withdrawal disabled: acceptance/withdrawal race contract unverified")
        own = self.list_own_matches()
        matches = [m for m in own.rows if m.challenge_id == challenge_id]
        if not own.complete or len(matches) != 1 or matches[0].status != "PROPOSED":
            raise SafetyError("Exact own proposal must currently be PROPOSED")
        # Human-confirmed withdrawal only. A fresh read does NOT guarantee atomicity.
        r = self.execute("withdraw", operation_key, {"challenge_id": challenge_id},
                         "/Player/WithdrawChallenge", data={"challengeId": str(challenge_id)})
        if r.state == "REJECTED":
            return r
        try:
            after = self.list_own_matches()
            if not after.complete or any(m.challenge_id == challenge_id for m in after.rows):
                raise UnknownOutcome("Withdrawal not verified")
        except Exception:
            self.journal.finish(operation_key, "UNKNOWN", challenge_id)
            raise UnknownOutcome("Withdrawal not verified; do not retry") from None
        self.journal.finish(operation_key, "VERIFIED", challenge_id)
        return WriteResult(operation_key, "VERIFIED", challenge_id)

    def accept_proposal(self, challenge_id, ladder_id, team_id, operation_key, *, confirmed=False):
        self.assert_write(confirmed)
        for value in [challenge_id, ladder_id, team_id]:
            positive(value)
        ladders = self.list_current_ladders()
        names = {l.name for l in ladders.rows if l.ladder_id == ladder_id}
        proposals = self.list_open_proposals()
        selected = [p for p in proposals.rows if p.challenge_id == challenge_id]
        if not proposals.complete or len(selected) != 1 or selected[0].ladder_name not in names or selected[0].accept_team_id != team_id:
            raise SafetyError("Exact proposal, eligibility and accepting team not established")
        r = self.execute("accept", operation_key,
                         {"challenge_id": challenge_id, "ladder_id": ladder_id, "team_id": team_id},
                         "/Player/AcceptProposal", params={"cId": challenge_id, "acceptedBy": team_id})
        if r.state == "REJECTED":
            return r
        try:
            after = self.list_own_matches()
            match = [m for m in after.rows if m.challenge_id == challenge_id and m.status == "ACCEPTED"]
            if not after.complete or len(match) != 1:
                raise UnknownOutcome("Acceptance not verified")
        except Exception:
            self.journal.finish(operation_key, "UNKNOWN", challenge_id)
            raise UnknownOutcome("Acceptance not verified; do not retry") from None
        self.journal.finish(operation_key, "VERIFIED", challenge_id)
        return WriteResult(operation_key, "VERIFIED", challenge_id)

    def report_score(self, score: ScoreInput, operation_key, *, confirmed=False):
        self.assert_write(confirmed)
        for value in [score.challenge_id, score.ladder_id, score.winner_team_id]:
            positive(value)
        if score.outcome not in ["PlayedThrough", "Injury", "Forfeit", "NoShow", "CourtTimeExpired"]:
            raise SafetyError("Unknown match outcome")
        if not re.fullmatch(r"[0-9(), \-]{1,120}", score.score):
            raise SafetyError("Invalid score syntax; use site-compatible numeric set notation")
        own = self.list_own_matches()
        rows = [m for m in own.rows if m.challenge_id == score.challenge_id and m.status == "ACCEPTED" and m.ladder_id == score.ladder_id]
        if not own.complete or len(rows) != 1:
            raise SafetyError("Exact accepted own match not established")
        page = self.transport.get(f"/Player/SubmitChallengeResult?ladderId={score.ladder_id}&challengeId={score.challenge_id}", private=True)
        s = parsers.soup(page)
        winner = s.select_one('select[name="WinnerId"]')
        hidden = s.select_one('input[name="challengeid"]')
        if not winner or str(score.winner_team_id) not in {o.get("value") for o in winner.select("option")} or not hidden or hidden.get("value") != str(score.challenge_id):
            raise SafetyError("Live score-entry identity changed")
        r = self.execute("score", operation_key, score, "/Team/SubmitChallengeScore",
                         data={"score": score.score, "challengeid": score.challenge_id,
                               "matchOutcome": score.outcome, "winnerId": score.winner_team_id})
        # History does not expose a stable challenge ID: never label this VERIFIED.
        return r

    @staticmethod
    def site_time(value):
        try:
            return datetime.strptime(value, "%m/%d/%Y %I:%M %p")
        except ValueError:
            raise SafetyError("Unrecognized site time; duplicate screening cannot be trusted") from None

    @staticmethod
    def proposal_time(p):
        return datetime.strptime(f"{p.match_date} {p.hour}:{p.minute:02d} {p.am_or_pm}", "%Y-%m-%d %I:%M %p")
