"""
Tests for molecular property prediction tools (ka_gat, ka_gnn).
"""

import os
from typing import Any, Dict

import pytest
from fastmcp import Client

MCP_URL = os.getenv("MCP_URL", "http://localhost:7002/mcp")

# Test SMILES
ETHANOL = "CCO"
BENZENE = "c1ccccc1"


@pytest.mark.asyncio
@pytest.mark.mcp
async def test_ka_gat():
    async with Client(MCP_URL) as client:

        async def call_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
            res = await client.call_tool(tool_name, kwargs or {})
            return getattr(res, "data", None) or {}

        result = await call_tool("ka_gat", smiles=ETHANOL, task="bbbp")
        assert result, f"ka_gat returned unexpected: {result}"


@pytest.mark.asyncio
@pytest.mark.mcp
async def test_ka_gat_all_tasks():
    async with Client(MCP_URL) as client:

        async def call_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
            res = await client.call_tool(tool_name, kwargs or {})
            return getattr(res, "data", None) or {}

        for task in ["bbbp", "clintox", "tox21", "sider"]:
            result = await call_tool("ka_gat", smiles=BENZENE, task=task)
            assert result, f"ka_gat {task} returned unexpected: {result}"


@pytest.mark.asyncio
@pytest.mark.mcp
async def test_ka_gnn():
    async with Client(MCP_URL) as client:

        async def call_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
            res = await client.call_tool(tool_name, kwargs or {})
            return getattr(res, "data", None) or {}

        result = await call_tool("ka_gnn", smiles=ETHANOL, task="bbbp")
        assert result, f"ka_gnn returned unexpected: {result}"


@pytest.mark.asyncio
@pytest.mark.mcp
async def test_ka_gnn_all_tasks():
    async with Client(MCP_URL) as client:

        async def call_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
            res = await client.call_tool(tool_name, kwargs or {})
            return getattr(res, "data", None) or {}

        for task in ["bbbp", "clintox", "tox21", "sider"]:
            result = await call_tool("ka_gnn", smiles=BENZENE, task=task)
            assert result, f"ka_gnn {task} returned unexpected: {result}"
