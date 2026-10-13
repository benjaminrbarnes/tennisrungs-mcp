"""Official MCP SDK stdio server. Writes unregistered unless operator enables them."""
import argparse

from mcp.server.fastmcp import FastMCP

from .models import IntegrationError, ProposalInput, ScoreInput
from .runtime import runtime
from .iparcs_reads import IParcsReads
from .runtime import operation_journal_path


def make_server(client, state_dir=None):
    mcp = FastMCP("tennisrungs")
    iparcs = IParcsReads()

    def call(fn, *args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            return result.to_dict() if hasattr(result, "to_dict") else result
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

    @mcp.tool()
    def iparcs_search_facilities(keyword: str) -> dict:
        """Anonymous Atlanta facility search. Observed query POST; no draft creation."""
        return call(iparcs.search, keyword)

    @mcp.tool()
    def iparcs_resource_detail(resource_id: int) -> dict:
        """Anonymous resource rules, detail and opening-hours read."""
        return call(iparcs.detail, resource_id)

    @mcp.tool()
    def iparcs_daily_availability(resource_id: int, start_date: str, end_date: str) -> dict:
        """Anonymous calendar read with complete date coverage; ISO dates, Atlanta time."""
        return call(iparcs.availability, resource_id, start_date, end_date)

    @mcp.tool()
    def iparcs_check_slot(resource_id: int, day: str, start_time: str, end_time: str) -> dict:
        """Check whole-block containment in one opening; no booking/hold. HH:MM:SS wall times."""
        return call(iparcs.check_slot, resource_id, day, start_time, end_time)

    @mcp.tool()
    def workflow_plan(intent: dict, observation: dict, now: str) -> dict:
        """Pure offline next-step preview. Input assertions are not verified authority. No live actions/timers."""
        from .workflow_api import plan
        return call(plan, intent, observation, now)

    @mcp.tool()
    def workflow_reconcile(intent: dict, observation: dict, now: str, operation_key: str) -> dict:
        """Read only the configured local operation journal; never clear it or retry a write."""
        from .workflow_api import reconcile_local
        return call(reconcile_local, intent, observation, now, operation_journal_path(state_dir), operation_key)

    @mcp.tool()
    def iparcs_preparation_plan(selection: dict, now: str) -> dict:
        """Offline protected-contract preview only. Selection/validation have unknown effects; no dispatch."""
        from .iparcs_planning import preparation_plan
        return call(preparation_plan, selection, now)

    @mcp.tool()
    def iparcs_compare_cart_snapshots(selection: dict, transactions: dict, summary: dict,
                                     browser_transactions: dict | None = None,
                                     browser_summary: dict | None = None,
                                     browser_url: str | None = None) -> dict:
        """Compare caller-supplied sanitized snapshots locally; does not navigate, authenticate or submit."""
        from .iparcs_planning import compare_cart
        return call(compare_cart, selection, transactions, summary, browser_transactions, browser_summary, browser_url)

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
        make_server(client, state_dir=args.state_dir).run(transport="stdio")
    finally:
        client.transport.close()
        if client.journal:
            client.journal.close()


if __name__ == "__main__":
    main()
