"""Official MCP SDK stdio server. Writes unregistered unless operator enables them."""
import argparse

from mcp.server.fastmcp import FastMCP

from .models import IntegrationError, ProposalInput, ScoreInput
from .runtime import runtime


def make_server(client):
    mcp = FastMCP("tennisrungs")

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs).to_dict()
        except IntegrationError as e:
            return {"error": type(e).__name__, "message": str(e)}
        except (TypeError, ValueError):
            return {"error": "InvalidInput", "message": "Invalid parameters; values suppressed"}

    @mcp.tool()
    def list_current_ladders() -> dict:
        """Read current authenticated membership. Requires approved session."""
        return call(client.list_current_ladders)

    @mcp.tool()
    def list_own_matches() -> dict:
        """Read own pending/proposed/accepted matches with coverage status."""
        return call(client.list_own_matches)

    @mcp.tool()
    def list_own_proposals() -> dict:
        """Read own PROPOSED matches. These may be absent from club open proposals."""
        return call(client.list_own_proposals)

    @mcp.tool()
    def list_open_proposals() -> dict:
        """Read club proposals. Rows may belong to ladders outside current membership."""
        return call(client.list_open_proposals)

    @mcp.tool()
    def get_rankings(ladder_id: int) -> dict:
        """Read exact ladder rankings; IDs are season-specific."""
        return call(client.get_rankings, ladder_id)

    @mcp.tool()
    def get_player_history(team_id: int) -> dict:
        """Read public history with original result orientation and score string."""
        return call(client.get_player_history, team_id)

    if client.writes_enabled:
        @mcp.tool()
        def propose_match(proposal: ProposalInput, operation_key: str, confirmed: bool = False) -> dict:
            """Posts to the whole ladder and sends notifications. Exact human authorization required."""
            return call(client.propose_match, proposal, operation_key, confirmed=confirmed)

        @mcp.tool()
        def withdraw_proposal(challenge_id: int, operation_key: str, confirmed: bool = False) -> dict:
            """Disabled for autonomous use until server acceptance-race behavior is validated."""
            return call(client.withdraw_proposal, challenge_id, operation_key, confirmed=confirmed, autonomous=True)

        @mcp.tool()
        def accept_proposal(challenge_id: int, ladder_id: int, team_id: int, operation_key: str, confirmed: bool = False) -> dict:
            """Accepts a selected proposal and commits a match. Specific human authorization required."""
            return call(client.accept_proposal, challenge_id, ladder_id, team_id, operation_key, confirmed=confirmed)

        @mcp.tool()
        def report_score(score: ScoreInput, operation_key: str, confirmed: bool = False) -> dict:
            """Submits a real result. Explicit authorization needed; acknowledgment is not verified history."""
            return call(client.report_score, score, operation_key, confirmed=confirmed)
    return mcp


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--keychain", action="store_true")
    p.add_argument("--enable-writes", action="store_true")
    p.add_argument("--state-dir")
    args = p.parse_args(argv)
    client = runtime(use_keychain=args.keychain, writes=args.enable_writes, state_dir=args.state_dir)
    try:
        make_server(client).run(transport="stdio")
    finally:
        client.transport.close()
        if client.journal:
            client.journal.close()


if __name__ == "__main__":
    main()
