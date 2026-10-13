import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_planning_smokes_have_no_live_dispatch(tmp_path):
    async def run():
        root = Path(__file__).parents[1]
        # Block connection attempts in the child without relying on sitecustomize.
        bootstrap = ("import socket,runpy\n"
                     "def denied(*a,**k): raise AssertionError('offline planning attempted network')\n"
                     "socket.create_connection=denied\n"
                     "socket.socket.connect=denied\n"
                     "socket.socket.connect_ex=denied\n"
                     "runpy.run_module('tennisrungs_mcp.server',run_name='__main__')\n")
        params = StdioServerParameters(command=sys.executable,
                                      args=["-c", bootstrap],
                                      env={**os.environ, "PYTHONPATH": str(root / "src")}, cwd=str(root))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                plan = json.loads((root / "examples/workflow.json").read_text())
                result = await session.call_tool("workflow_plan", plan)
                body = json.loads(result.content[0].text)
                assert body["decision"]["action"] == "WAIT"
                assert body["live_execution_enabled"] is False and body["timer_installed"] is False
                prep = json.loads((root / "examples/iparcs-preparation.json").read_text())
                result = await session.call_tool("iparcs_preparation_plan", prep)
                body = json.loads(result.content[0].text)
                assert body["live_execution_enabled"] is False
                assert "checkout" in body["hard_denied"]
    asyncio.run(run())
