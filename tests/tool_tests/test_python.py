import os
from typing import Any, Dict

import pytest
from fastmcp import Client

MCP_URL = os.getenv("MCP_URL", "http://localhost:7002/mcp")


@pytest.mark.asyncio
@pytest.mark.mcp
async def test_code_execution():
    async with Client(MCP_URL) as client:

        async def call_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
            res = await client.call_tool(tool_name, kwargs or {})
            return getattr(res, "data", None) or {}

        ex = await call_tool(
            "execute_python_code",
            code='print("hi-from-code")\n',
            timeout=15,
            parent="/tmp/code",
            filename="hello.py",
            save_to_file=True,
        )
        assert "error" not in ex, f"execute_python_code failed: {ex}"
        assert "hi-from-code" in ex.get(
            "stdout", ""
        ), f"execute_python_code stdout mismatch: {ex}"
        file_path = ex.get("file_path")
        assert file_path, f"execute_python_code missing file_path: {ex}"

        # execute_python_script expects a session-relative path (e.g. /tmp/code/hello.py),
        # not the absolute session-internal path returned by execute_python_code.
        ex2 = await call_tool(
            "execute_python_script",
            script_path="/tmp/code/hello.py",
            args=["--flag"],
            timeout=15,
            cwd_path="/tmp/code",
        )
        assert "error" not in ex2, f"execute_python_script failed: {ex2}"
        assert "hi-from-code" in ex2.get(
            "stdout", ""
        ), f"execute_python_script stdout mismatch: {ex2}"
