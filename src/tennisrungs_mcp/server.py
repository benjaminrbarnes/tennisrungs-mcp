"""Read-only MCP server. Login is a separate, local CLI operation."""
import argparse
import os


def strip_credential_environment():
    for name in list(os.environ):
        if (name in {"TENNISRUNGS_USERNAME", "TENNISRUNGS_PASSWORD"}
                or name.startswith("OP_") or name.startswith("TENNIS_CREDENTIAL_")):
            os.environ.pop(name, None)


strip_credential_environment()

from mcp.server.fastmcp import FastMCP
from .models import IntegrationError
from .runtime import runtime


def make_server(client):
    mcp = FastMCP("tennisrungs")

    def call(function, *args):
        try:
            return function(*args).to_dict()
        except IntegrationError as exc:
            return {"error": type(exc).__name__, "message": str(exc)}
        except (TypeError, ValueError):
            return {"error": "InvalidInput", "message": "Invalid parameters; values suppressed"}

    @mcp.tool()
    def list_current_ladders() -> dict:
        """Read current authenticated ladder membership and coverage."""
        return call(client.list_current_ladders)

    @mcp.tool()
    def list_own_matches() -> dict:
        """Read own pending, proposed and accepted matches with coverage."""
        return call(client.list_own_matches)

    @mcp.tool()
    def list_own_proposals() -> dict:
        """Read own proposed matches, separately from club-wide proposals."""
        return call(client.list_own_proposals)

    @mcp.tool()
    def list_open_proposals() -> dict:
        """Read club-wide proposals; these can include other seasons/ladders."""
        return call(client.list_open_proposals)

    @mcp.tool()
    def get_rankings(ladder_id: int) -> dict:
        """Read an exact ladder's standings. IDs are season-specific."""
        return call(client.get_rankings, ladder_id)

    @mcp.tool()
    def get_player_history(team_id: int) -> dict:
        """Read public player history, preserving original scores and result orientation."""
        return call(client.get_player_history, team_id)

    return mcp


def main(argv=None):
    strip_credential_environment()
    parser = argparse.ArgumentParser(description="Read-only TennisRungs MCP over stdio")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--file-session", action="store_true", help="Use a session created by the local login CLI")
    group.add_argument("--keychain", action="store_true", help="Use the legacy macOS Keychain session")
    args = parser.parse_args(argv)
    client = runtime(use_keychain=args.keychain, use_file_session=args.file_session)
    try:
        make_server(client).run(transport="stdio")
    finally:
        client.transport.close()


if __name__ == "__main__":
    main()
