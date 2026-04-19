import os
from typing import Any, Dict

import pytest
from fastmcp import Client

MCP_URL = os.getenv("MCP_URL", "http://localhost:7002/mcp")


@pytest.mark.asyncio
@pytest.mark.mcp
async def test_filesystem_roundtrip():
    async with Client(MCP_URL) as client:

        async def call_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
            res = await client.call_tool(tool_name, kwargs or {})
            return getattr(res, "data", None) or {}

        mk = await call_tool("fs_mkdir", path="testdir")
        assert "error" not in mk, f"fs_mkdir testdir failed: {mk}"
        base = mk.get("path", "testdir")

        w = await call_tool(
            "fs_write", path=f"{base}/hello.txt", content="hello world", mode="text"
        )
        assert "error" not in w, f"fs_write failed: {w}"
        vpath = w["path"]

        ls = await call_tool("fs_list", path=base)
        assert "error" not in ls, f"fs_list failed: {ls}"
        assert any(
            e["name"] == "hello.txt" for e in ls.get("entries", [])
        ), f"fs_list missing hello.txt: {ls}"

        mk2 = await call_tool("fs_mkdir", path="testdir2")
        assert "error" not in mk2, f"fs_mkdir testdir2 failed: {mk2}"

        mv = await call_tool(
            "fs_move", src=vpath, dst="testdir2/goodbye.txt", overwrite=True
        )
        assert "error" not in mv, f"fs_move failed: {mv}"
        moved = mv["dst"]

        rd = await call_tool("fs_read", path=moved)
        assert "error" not in rd, f"fs_read failed: {rd}"
        assert rd.get("text") == "hello world", f"fs_read mismatch: {rd}"

        for target, kw in [
            (moved, {}),
            ("testdir2", {"recursive": True}),
            ("testdir", {"recursive": True}),
        ]:
            rm = await call_tool("fs_remove", path=target, **kw)
            assert "error" not in rm, f"fs_remove {target} failed: {rm}"
