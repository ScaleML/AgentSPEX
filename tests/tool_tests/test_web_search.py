import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict

import pytest
from dotenv import dotenv_values
from fastmcp import Client

# Load VM env config
_VM_ENV_PATH = Path(__file__).resolve().parents[2] / "config" / "vm.env"
_VM_CONFIG = dotenv_values(_VM_ENV_PATH)

MCP_URL = os.getenv("MCP_URL", "http://localhost:7002/mcp")


async def _call_tool(client: Client, tool_name: str, **kwargs) -> Any:
    res = await client.call_tool(tool_name, kwargs or {})
    data = getattr(res, "data", None)
    return data if data is not None else {}


@pytest.mark.mcp
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _VM_CONFIG.get("FIRECRAWL_API_KEY"),
    reason="Requires FIRECRAWL_API_KEY in vm.env",
)
async def test_firecrawl_search_basic():
    """
    Test firecrawl_search returns results with url and local_filename.
    Requires FIRECRAWL_API_KEY in config/vm.env.
    """
    async with Client(MCP_URL) as client:
        out = await _call_tool(
            client,
            "firecrawl_search",
            query="python async programming",
            num_results=2,
        )
        assert isinstance(out, list), f"expected list, got: {type(out)}"
        assert len(out) <= 2, f"expected at most 2 results, got: {len(out)}"
        for result in out:
            assert "url" in result, f"missing 'url' in result: {result}"
            assert (
                "local_filename" in result
            ), f"missing 'local_filename' in result: {result}"
            assert result["local_filename"].endswith(
                ".md"
            ), f"expected .md file: {result['local_filename']}"
