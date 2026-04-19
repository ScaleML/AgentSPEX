"""
Unit tests for the episodic memory tool
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from sandbox_vm.tools.memory.episodic import _load_memory, _save_memory, memory


class TestEpisodicMemory:
    """Test suite for episodic memory functionality"""

    @pytest.fixture
    def temp_memory_file(self):
        """Create a temporary memory file for testing"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
        # Also cleanup temp file if it exists
        if os.path.exists(temp_path + ".tmp"):
            os.remove(temp_path + ".tmp")

    @pytest.mark.asyncio
    async def test_load_empty_memory(self, temp_memory_file):
        """Test loading an empty/non-existent memory file"""
        result = await _load_memory(temp_memory_file)
        assert result == {}

    @pytest.mark.asyncio
    async def test_save_and_load_memory(self, temp_memory_file):
        """Test saving and loading memory data"""
        test_data = {
            "key1": {"content": "test content", "tags": ["tag1"], "timestamp": 123.456}
        }

        success = await _save_memory(test_data, temp_memory_file)
        assert success is True

        loaded_data = await _load_memory(temp_memory_file)
        assert loaded_data == test_data

    @pytest.mark.asyncio
    async def test_store_action(self, temp_memory_file):
        """Test storing a memory entry"""
        result = await memory(
            action="store",
            memory_file=temp_memory_file,
            key="test_key",
            content="This is test content",
            tags="test,memory,unit",
        )

        assert "error" not in result
        assert "Stored 'test_key'" in result["result"]

        # Verify the entry was actually saved
        loaded_data = await _load_memory(temp_memory_file)
        assert "test_key" in loaded_data
        assert loaded_data["test_key"]["content"] == "This is test content"
        assert set(loaded_data["test_key"]["tags"]) == {"test", "memory", "unit"}

    @pytest.mark.asyncio
    async def test_store_without_tags(self, temp_memory_file):
        """Test storing a memory entry without tags"""
        result = await memory(
            action="store",
            memory_file=temp_memory_file,
            key="test_key2",
            content="Content without tags",
            tags="",
        )

        assert "error" not in result
        loaded_data = await _load_memory(temp_memory_file)
        assert loaded_data["test_key2"]["tags"] == []

    @pytest.mark.asyncio
    async def test_store_missing_key(self, temp_memory_file):
        """Test that store fails without key"""
        result = await memory(
            action="store", memory_file=temp_memory_file, key="", content="test content"
        )

        assert "error" in result
        assert "requires both 'key' and 'content'" in result["error"]

    @pytest.mark.asyncio
    async def test_store_missing_content(self, temp_memory_file):
        """Test that store fails without content"""
        result = await memory(
            action="store", memory_file=temp_memory_file, key="test_key", content=""
        )

        assert "error" in result
        assert "requires both 'key' and 'content'" in result["error"]

    @pytest.mark.asyncio
    async def test_get_action(self, temp_memory_file):
        """Test retrieving a memory entry"""
        # First store an entry
        await memory(
            action="store",
            memory_file=temp_memory_file,
            key="retrieve_test",
            content="Content to retrieve",
            tags="retrieve",
        )

        # Now retrieve it
        result = await memory(
            action="get", memory_file=temp_memory_file, key="retrieve_test"
        )

        assert "error" not in result
        assert result["result"] == "Content to retrieve"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, temp_memory_file):
        """Test getting a non-existent key"""
        result = await memory(
            action="get", memory_file=temp_memory_file, key="nonexistent"
        )

        assert "error" not in result
        assert "No entry found" in result["result"]

    @pytest.mark.asyncio
    async def test_get_missing_key_param(self, temp_memory_file):
        """Test that get fails without key parameter"""
        result = await memory(action="get", memory_file=temp_memory_file, key="")

        assert "error" in result
        assert "requires 'key' parameter" in result["error"]

    @pytest.mark.asyncio
    async def test_search_by_tag(self, temp_memory_file):
        """Test searching by tag"""
        # Store multiple entries
        await memory(
            "store", temp_memory_file, "key1", "Content 1", "python,programming"
        )
        await memory(
            "store", temp_memory_file, "key2", "Content 2", "javascript,programming"
        )
        await memory("store", temp_memory_file, "key3", "Content 3", "cooking,recipe")

        # Search for programming tag
        result = await memory(
            action="search", memory_file=temp_memory_file, query="programming"
        )

        assert "error" not in result
        assert "Found 2 matches" in result["result"]
        assert "key1" in result["result"]
        assert "key2" in result["result"]
        assert "key3" not in result["result"]

    @pytest.mark.asyncio
    async def test_search_by_content(self, temp_memory_file):
        """Test searching by content"""
        await memory(
            "store", temp_memory_file, "key1", "Machine learning algorithms", "ml,ai"
        )
        await memory(
            "store", temp_memory_file, "key2", "Deep learning networks", "ml,ai"
        )
        await memory("store", temp_memory_file, "key3", "Cooking recipes", "food")

        result = await memory(
            action="search", memory_file=temp_memory_file, query="learning"
        )

        assert "error" not in result
        assert "Found 2 matches" in result["result"]

    @pytest.mark.asyncio
    async def test_search_no_results(self, temp_memory_file):
        """Test search with no results"""
        await memory("store", temp_memory_file, "key1", "Content 1", "tag1")

        result = await memory(
            action="search", memory_file=temp_memory_file, query="nonexistent"
        )

        assert "error" not in result
        assert "No results found" in result["result"]

    @pytest.mark.asyncio
    async def test_search_missing_query(self, temp_memory_file):
        """Test that search fails without query parameter"""
        result = await memory(action="search", memory_file=temp_memory_file, query="")

        assert "error" in result
        assert "requires 'query' parameter" in result["error"]

    @pytest.mark.asyncio
    async def test_recent_action(self, temp_memory_file):
        """Test getting recent entries"""
        # Store entries with small delays to ensure different timestamps
        await memory("store", temp_memory_file, "key1", "First entry", "tag1")
        await asyncio.sleep(0.01)
        await memory("store", temp_memory_file, "key2", "Second entry", "tag2")
        await asyncio.sleep(0.01)
        await memory("store", temp_memory_file, "key3", "Third entry", "tag3")

        result = await memory(action="recent", memory_file=temp_memory_file, limit=2)

        assert "error" not in result
        assert "Recent 2 entries" in result["result"]
        # Most recent should appear first
        assert result["result"].index("key3") < result["result"].index("key2")

    @pytest.mark.asyncio
    async def test_recent_empty_memory(self, temp_memory_file):
        """Test recent on empty memory"""
        result = await memory(action="recent", memory_file=temp_memory_file)

        assert "error" not in result
        assert "No memory entries found" in result["result"]

    @pytest.mark.asyncio
    async def test_stats_action(self, temp_memory_file):
        """Test memory statistics"""
        # Store some entries
        await memory("store", temp_memory_file, "key1", "Content 1", "tag1,tag2")
        await memory("store", temp_memory_file, "key2", "Content 2", "tag2,tag3")
        await memory("store", temp_memory_file, "key3", "Content 3", "tag3")

        result = await memory(action="stats", memory_file=temp_memory_file)

        assert "error" not in result
        assert "Total entries: 3" in result["result"]
        assert "Unique tags: 3" in result["result"]
        assert temp_memory_file in result["result"]

    @pytest.mark.asyncio
    async def test_stats_empty_memory(self, temp_memory_file):
        """Test stats on empty memory"""
        result = await memory(action="stats", memory_file=temp_memory_file)

        assert "error" not in result
        assert "Memory is empty" in result["result"]

    @pytest.mark.asyncio
    async def test_clear_action(self, temp_memory_file):
        """Test clearing all memory"""
        # Store some entries
        await memory("store", temp_memory_file, "key1", "Content 1", "tag1")
        await memory("store", temp_memory_file, "key2", "Content 2", "tag2")

        # Verify entries exist
        loaded_data = await _load_memory(temp_memory_file)
        assert len(loaded_data) == 2

        # Clear memory
        result = await memory(action="clear", memory_file=temp_memory_file)

        assert "error" not in result
        assert "2 entries removed" in result["result"]

        # Verify memory is empty
        loaded_data = await _load_memory(temp_memory_file)
        assert len(loaded_data) == 0

    @pytest.mark.asyncio
    async def test_invalid_action(self, temp_memory_file):
        """Test invalid action"""
        result = await memory(action="invalid_action", memory_file=temp_memory_file)

        assert "error" in result
        assert "Unknown action" in result["error"]

    @pytest.mark.asyncio
    async def test_access_count_tracking(self, temp_memory_file):
        """Test that access count is tracked"""
        # Store an entry
        await memory("store", temp_memory_file, "tracked_key", "Content", "tag")

        # Retrieve it multiple times
        await memory("get", temp_memory_file, key="tracked_key")
        await memory("get", temp_memory_file, key="tracked_key")
        await memory("get", temp_memory_file, key="tracked_key")

        # Check access count
        loaded_data = await _load_memory(temp_memory_file)
        assert loaded_data["tracked_key"]["access_count"] == 3
        assert "last_accessed" in loaded_data["tracked_key"]

    @pytest.mark.asyncio
    async def test_content_truncation_in_search(self, temp_memory_file):
        """Test that long content is truncated in search results"""
        long_content = "x" * 300  # Content longer than 200 chars
        await memory("store", temp_memory_file, "long_key", long_content, "test")

        result = await memory(
            action="search", memory_file=temp_memory_file, query="test"
        )

        assert "error" not in result
        # Should contain truncation indicator
        assert "..." in result["result"]

    @pytest.mark.asyncio
    async def test_memory_directory_creation(self):
        """Test that memory directory is created if it doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_file = os.path.join(tmpdir, "subdir", "memory.json")

            result = await memory(
                action="store",
                memory_file=memory_file,
                key="test",
                content="test content",
            )

            assert "error" not in result
            assert os.path.exists(memory_file)

    @pytest.mark.asyncio
    async def test_case_insensitive_search(self, temp_memory_file):
        """Test that search is case-insensitive"""
        await memory("store", temp_memory_file, "key1", "Python Programming", "Python")

        result = await memory(
            action="search", memory_file=temp_memory_file, query="python"
        )

        assert "error" not in result
        assert "Found 1 matches" in result["result"]

    @pytest.mark.asyncio
    async def test_tag_normalization(self, temp_memory_file):
        """Test that tags are normalized to lowercase"""
        await memory(
            action="store",
            memory_file=temp_memory_file,
            key="key1",
            content="Content",
            tags="Python,PROGRAMMING,Test",
        )

        loaded_data = await _load_memory(temp_memory_file)
        assert loaded_data["key1"]["tags"] == ["python", "programming", "test"]
