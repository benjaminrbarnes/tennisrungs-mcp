import pytest

from tennisrungs_mcp import parsers
from tennisrungs_mcp.models import UnsupportedContract
from fixtures import dashboard, HISTORY, RANKINGS, FORM


def test_own_proposal_identity_and_schedule():
    m = parsers.my_matches(dashboard())[0]
    assert (m.challenge_id, m.ladder_id, m.status) == (303, 101, "PROPOSED")
    assert m.scheduled_text == "10/20/2099 10:00 AM"
    assert m.venue == "Demo Court"


def test_club_proposals_are_separate_and_include_season_team():
    p = parsers.open_proposals(dashboard(own=False))[0]
    assert (p.challenge_id, p.accept_team_id) == (303, 201)
    assert not parsers.my_matches(dashboard(own=False))


def test_membership_deduplicates_ladder_links():
    assert parsers.current_ladders(dashboard())[0].ladder_id == 101


def test_history_preserves_orientation_and_nonstandard_suffix():
    h = parsers.history(HISTORY)
    assert h[0].result == "L"
    assert h[0].score == "6-3,7-6 (10-8)"
    assert h[1].score.endswith("Forfeit")


def test_rankings_use_team_not_ladder_id():
    assert parsers.rankings(RANKINGS)[0].team_id == 201


@pytest.mark.parametrize("parser", [parsers.history, parsers.rankings, parsers.my_matches, parsers.open_proposals, parsers.current_ladders])
def test_schema_drift_is_not_empty_success(parser):
    with pytest.raises(UnsupportedContract):
        parser("<html>unexpected structure</html>")


def test_count_and_pagination_fail_closed():
    h = dashboard().replace("My Challenges (1)", "My Challenges (4)")
    assert not parsers.coverage(h, parsers.my_matches(h), "My Challenges")[0]
    assert not parsers.coverage(HISTORY + '<a rel="next">Next</a>', [], None)[0]


def test_form_preserves_token_without_treating_it_as_bearer():
    defaults, options = parsers.proposal_form(FORM)
    assert ("__RequestVerificationToken", "synthetic-test-only") in defaults
    assert options["Location"] == {"401": "Demo Court"}


def test_missing_count_never_establishes_write_coverage():
    h = dashboard().replace("My Challenges (1)", "My Challenges")
    complete, warnings = parsers.coverage(h, parsers.my_matches(h), "My Challenges")
    assert not complete and "Expected displayed count not found" in warnings


def test_conflicting_row_ids_fail_closed():
    h = dashboard().replace("challengeId=303", "challengeId=999")
    with pytest.raises(UnsupportedContract, match="Conflicting"):
        parsers.my_matches(h)


def test_history_column_reordering_preserves_orientation():
    h = '''<table><tr><th>Score</th><th>Result</th><th>Vs.</th><th>Date</th></tr>
    <tr><td>6-3,7-6</td><td>L</td><td><a href="/Public/PlayerMatches?teamId=202">Demo Other</a></td><td>10/1/2099</td></tr></table>'''
    row = parsers.history(h)[0]
    assert row.date == "10/1/2099" and row.result == "L" and row.score == "6-3,7-6"


def test_malformed_history_row_is_not_silently_dropped():
    with pytest.raises(UnsupportedContract, match="row"):
        parsers.history(HISTORY.replace('<td>L</td>', ''))
