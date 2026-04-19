"""Tests for BM25S retrieval tools (bm25_index and bm25_search)."""

import os
from typing import Any, Dict

import pytest
from fastmcp import Client

try:
    from sandbox_vm.tools.retrieval.bm25_index import bm25_index
    from sandbox_vm.tools.retrieval.bm25_search import bm25_search

    _HAS_BM25S = True
except ImportError:
    _HAS_BM25S = False

pytestmark = pytest.mark.skipif(not _HAS_BM25S, reason="bm25s not installed")

MCP_URL = os.getenv("MCP_URL", "http://localhost:7002/mcp")


@pytest.fixture(autouse=True)
def tmp_index_root(monkeypatch, tmp_path):
    """Point both tools at a temp directory for index storage."""
    root = str(tmp_path / "indices")
    monkeypatch.setattr("sandbox_vm.tools.retrieval.bm25_index._INDEX_ROOT", root)
    monkeypatch.setattr("sandbox_vm.tools.retrieval.bm25_search._INDEX_ROOT", root)
    return root


# ── bm25_index ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_index_from_documents(tmp_index_root):
    docs = ["cat on the mat", "dog in the park", "fish in the river"]
    result = await bm25_index(collection="test_docs", documents=docs)

    assert "error" not in result
    assert result["collection"] == "test_docs"
    assert result["num_documents"] == 3
    assert os.path.isdir(result["index_dir"])


@pytest.mark.asyncio
async def test_index_empty_documents(tmp_index_root):
    result = await bm25_index(collection="empty_list", documents=[])
    assert "error" in result


# ── bm25_search ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_basic(tmp_index_root):
    docs = [
        "the cat sat on the mat",
        "the dog chased the ball in the park",
        "a fish swam in the river under the bridge",
    ]
    await bm25_index(collection="animals", documents=docs)

    result = await bm25_search(collection="animals", query="cat mat", k=2)

    assert "error" not in result
    assert len(result["queries"]) == 1
    top = result["queries"][0]["results"]
    assert len(top) == 2
    assert top[0]["score"] >= top[1]["score"]
    assert "cat" in top[0]["text"]


@pytest.mark.asyncio
async def test_search_multiple_queries(tmp_index_root):
    docs = ["alpha beta gamma", "delta epsilon zeta", "eta theta iota"]
    await bm25_index(collection="greek", documents=docs)

    result = await bm25_search(collection="greek", query="alpha\nzeta", k=1)

    assert "error" not in result
    assert len(result["queries"]) == 2
    assert "alpha" in result["queries"][0]["results"][0]["text"]
    assert "zeta" in result["queries"][1]["results"][0]["text"]


@pytest.mark.asyncio
async def test_search_collection_not_found(tmp_index_root):
    result = await bm25_search(collection="nonexistent", query="hello")
    assert "error" in result
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_search_empty_query(tmp_index_root):
    await bm25_index(collection="q_test", documents=["some text here"])

    result = await bm25_search(collection="q_test", query="")
    assert "error" in result


@pytest.mark.asyncio
async def test_search_k_larger_than_corpus(tmp_index_root):
    await bm25_index(collection="tiny", documents=["one document only"])

    result = await bm25_search(collection="tiny", query="document", k=100)

    assert "error" not in result
    assert len(result["queries"][0]["results"]) == 1


@pytest.mark.asyncio
async def test_search_text_truncation(tmp_index_root):
    long_text = "word " * 200  # 1000 chars
    await bm25_index(collection="long", documents=[long_text])

    result = await bm25_search(collection="long", query="word", k=1)

    assert "error" not in result
    assert len(result["queries"][0]["results"][0]["text"]) <= 500


# ── MCP integration ─────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.mcp
async def test_bm25_index_and_search_via_mcp():
    """Index documents and search them through the MCP server."""
    async with Client(MCP_URL) as client:

        async def call_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
            res = await client.call_tool(tool_name, kwargs or {})
            return getattr(res, "data", None) or {}

        idx = await call_tool(
            "bm25_index",
            collection="mcp_integration_test",
            documents=[
                "quantum computing uses qubits for parallel computation",
                "classical computers use binary bits for processing",
                "machine learning models learn patterns from data",
            ],
        )
        assert "error" not in idx, f"bm25_index failed: {idx}"
        assert idx["num_documents"] == 3

        res = await call_tool(
            "bm25_search",
            collection="mcp_integration_test",
            query="quantum qubits",
            k=2,
        )
        assert "error" not in res, f"bm25_search failed: {res}"
        top = res["queries"][0]["results"]
        assert len(top) == 2
        assert "quantum" in top[0]["text"]
