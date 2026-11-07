"""Read-only TennisRungs operations with explicit coverage and season IDs."""
from datetime import datetime, timezone

from . import parsers
from .models import ReadResult, IntegrationError
from .transport import BASE


def positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise IntegrationError("IDs must be positive integers")
    return value


class Client:
    def __init__(self, transport):
        self.transport = transport

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
        result = self.list_own_matches()
        return ReadResult(result.source_url, result.observed_at,
                          [m for m in result.rows if m.status == "PROPOSED"],
                          result.complete, result.warnings)

    def list_open_proposals(self):
        path = "/Player"
        html = self.transport.get(path, private=True)
        return self.result(path, html, parsers.open_proposals(html), "Open Proposals")

    def get_rankings(self, ladder_id):
        path = f"/Ladders/Rankings/{positive(ladder_id)}"
        html = self.transport.get(path, private=True)
        return self.result(path, html, parsers.rankings(html))

    def get_player_history(self, team_id):
        path = f"/Public/PlayerMatches?teamId={positive(team_id)}"
        html = self.transport.get(path)
        return self.result(path, html, parsers.history(html))
