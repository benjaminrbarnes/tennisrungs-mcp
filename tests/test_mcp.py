import asyncio
import os
import sys
from pathlib import Path
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tennisrungs_mcp import cli, server

READ_TOOLS = {"list_current_ladders", "list_own_matches", "list_own_proposals",
              "list_open_proposals", "get_rankings", "get_player_history"}


def test_stdio_initialization_and_unconfigured_account_read():
    async def check():
        root = Path(__file__).parents[1]
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "tennisrungs_mcp.server"],
            env={**os.environ, "PYTHONPATH": str(root / "src")}, cwd=str(root))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                assert {t.name for t in (await session.list_tools()).tools} == READ_TOOLS
                result = await session.call_tool("list_own_matches", {})
                assert "AuthenticationRequired" in result.content[0].text
    asyncio.run(check())


@pytest.mark.parametrize("args", [["propose"], ["score"], ["accept"], ["withdraw"], ["iparcs"], ["--enable-writes", "matches"]])
def test_removed_cli_actions_are_not_available(args):
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2


def test_server_cannot_enable_writes():
    with pytest.raises(SystemExit) as exc:
        server.main(["--enable-writes"])
    assert exc.value.code == 2


def test_server_discards_inherited_passwords(monkeypatch):
    for key in ["TENNISRUNGS_PASSWORD", "OP_SERVICE_ACCOUNT_TOKEN", "TENNIS_CREDENTIAL_PASSWORD"]:
        monkeypatch.setenv(key, "synthetic-secret")
    server.strip_credential_environment()
    assert not any(k in os.environ for k in ["TENNISRUNGS_PASSWORD", "OP_SERVICE_ACCOUNT_TOKEN", "TENNIS_CREDENTIAL_PASSWORD"])
