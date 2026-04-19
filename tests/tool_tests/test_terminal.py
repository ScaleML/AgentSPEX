import os
from typing import Any, Dict

import pytest
from fastmcp import Client

MCP_URL = os.getenv("MCP_URL", "http://localhost:7002/mcp")


@pytest.mark.asyncio
@pytest.mark.mcp
async def test_terminal():
    async with Client(MCP_URL) as client:

        async def call_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
            res = await client.call_tool(tool_name, kwargs or {})
            return getattr(res, "data", None) or {}

        s1 = await call_tool("term_send", text="echo terminal_ok")
        assert "error" not in s1, f"term_send failed: {s1}"

        r1 = await call_tool("term_read", lines=50)
        assert "error" not in r1, f"term_read failed: {r1}"
        assert "terminal_ok" in r1.get("output", ""), f"term_read missing echo: {r1}"

        r2 = await call_tool("shell_run", text="echo shellrun_ok")
        assert "error" not in r2, f"shell_run failed: {r2}"
        assert "shellrun_ok" in r2.get("output", ""), f"shell_run output mismatch: {r2}"
