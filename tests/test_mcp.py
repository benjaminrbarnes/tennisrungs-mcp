import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_initialize_tools_and_fail_closed_account_read():
    async def run():
        root = Path(__file__).parents[1]
        params = StdioServerParameters(command=sys.executable,
                                      args=["-m", "tennisrungs_mcp.server"],
                                      env={**os.environ, "PYTHONPATH": str(root / "src")}, cwd=str(root))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert names == {"list_current_ladders", "list_own_matches", "list_own_proposals", "list_open_proposals", "get_rankings", "get_player_history"}
                result = await session.call_tool("list_own_matches", {})
                assert "AuthenticationRequired" in result.content[0].text
    asyncio.run(run())


def test_write_tool_schema_has_separate_confirmation_and_withdraw_refuses(tmp_path):
    from tennisrungs_mcp.server import make_server
    from tennisrungs_mcp.client import Client
    from tennisrungs_mcp.journal import Journal
    async def run():
        server = make_server(Client(None, Journal(tmp_path / "ops.sqlite3"), writes_enabled=True))
        tools = await server.list_tools()
        tool = next(t for t in tools if t.name == "propose_match")
        assert "proposal" in tool.inputSchema["properties"]
        assert "confirmed" in tool.inputSchema["properties"]
        result = await server.call_tool("withdraw_proposal", {"challenge_id": 303, "operation_key": "one", "confirmed": True})
        assert "race" in str(result)
    asyncio.run(run())
