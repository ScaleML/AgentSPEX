"""
Unit tests for checkpoints/checkpoint_manager.py

Tests the checkpoint manager functionality including:
- Checkpoint creation and loading
- Step completion tracking
- Metadata persistence
- Workspace backup and restore
"""

import shutil
import tempfile
import threading
from pathlib import Path

import pytest

from harness.checkpoints import CheckpointManager


class TestCheckpointManager:
    """Tests for the CheckpointManager class"""

    @pytest.fixture
    def checkpoint_dir(self, tmp_path):
        """Create a temporary checkpoint directory"""
        checkpoint_path = tmp_path / "checkpoint.json"
        yield checkpoint_path

    def test_init_creates_empty(self, checkpoint_dir):
        """Test that new checkpoint manager starts empty"""
        cm = CheckpointManager(checkpoint_dir)
        assert not cm.loaded
        assert cm.completed_steps == set()

    def test_mark_completed(self, checkpoint_dir):
        """Test marking a step as completed"""
        cm = CheckpointManager(checkpoint_dir)
        cm.mark_completed("1")
        assert cm.is_completed("1")
        assert not cm.is_completed("2")

        # Verify persistence
        cm2 = CheckpointManager(checkpoint_dir)
        assert cm2.loaded
        assert cm2.is_completed("1")

    def test_submodule_steps(self, checkpoint_dir):
        """Test marking submodule steps as completed"""
        cm = CheckpointManager(checkpoint_dir)
        cm.mark_completed("1.1")
        cm.mark_completed("1.2")

        assert cm.is_completed("1.1")
        assert cm.is_completed("1.2")
        assert not cm.is_completed("1")

    def test_metadata_persistence(self, checkpoint_dir):
        """Test metadata is persisted across sessions"""
        cm = CheckpointManager(checkpoint_dir)
        cm.set_metadata("foo", "bar")
        assert cm.get_metadata("foo") == "bar"

        cm2 = CheckpointManager(checkpoint_dir)
        assert cm2.get_metadata("foo") == "bar"

    def test_mark_completed_with_context(self, checkpoint_dir):
        """Test marking completed with context update"""
        cm = CheckpointManager(checkpoint_dir)
        context = {"a": 1}
        cm.mark_completed("1", context=context, update_context=True)

        cm2 = CheckpointManager(checkpoint_dir)
        assert cm2.data["context"] == {"a": 1}

    def test_concurrency_simulation(self, checkpoint_dir):
        """Test that concurrent access doesn't crash"""
        cm = CheckpointManager(checkpoint_dir)

        def worker(i):
            cm.mark_completed(f"step_{i}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(cm.completed_steps) == 10
        cm2 = CheckpointManager(checkpoint_dir)
        assert len(cm2.completed_steps) == 10

    def test_backup_workspace_shutil(self, checkpoint_dir, tmp_path):
        """Test workspace backup using shutil"""
        cm = CheckpointManager(checkpoint_dir)

        # Create source workspace with files
        source_dir = tmp_path / "workspace"
        source_dir.mkdir()
        (source_dir / "test_file.txt").write_text("hello world")
        (source_dir / "subdir").mkdir()
        (source_dir / "subdir" / "nested.txt").write_text("nested content")

        # Backup
        target_dir = tmp_path / "backup"
        result = cm.backup_workspace(source_dir, target_dir)

        assert result
        assert (target_dir / "test_file.txt").exists()
        assert (target_dir / "test_file.txt").read_text() == "hello world"
        assert (target_dir / "subdir" / "nested.txt").exists()

        # Check metadata updated
        assert cm.get_metadata("workspace_backup_path") == str(target_dir)
        assert cm.data.get("backups") is not None
        assert len(cm.data["backups"]) == 1

    def test_restore_workspace(self, checkpoint_dir, tmp_path):
        """Test workspace restore from backup"""
        cm = CheckpointManager(checkpoint_dir)

        # Create backup directory with files
        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        (backup_dir / "restored_file.txt").write_text("restored content")
        (backup_dir / "subdir").mkdir()
        (backup_dir / "subdir" / "data.txt").write_text("data content")

        # Restore to new target
        target_dir = tmp_path / "restored_workspace"
        result = cm.restore_workspace(backup_dir, target_dir)

        assert result
        assert (target_dir / "restored_file.txt").exists()
        assert (target_dir / "restored_file.txt").read_text() == "restored content"
        assert (target_dir / "subdir" / "data.txt").exists()

        # Check metadata updated
        assert cm.data.get("restores") is not None
        assert len(cm.data["restores"]) == 1

    def test_restore_nonexistent_backup(self, checkpoint_dir, tmp_path):
        """Test restore returns False when backup doesn't exist"""
        cm = CheckpointManager(checkpoint_dir)

        backup_dir = tmp_path / "nonexistent"
        target_dir = tmp_path / "target"

        result = cm.restore_workspace(backup_dir, target_dir)
        assert not result

    def test_backup_and_restore_roundtrip(self, checkpoint_dir, tmp_path):
        """Test full backup -> modify -> restore cycle"""
        cm = CheckpointManager(checkpoint_dir)

        # Create original workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "original.txt").write_text("original content")

        # Backup
        backup_dir = tmp_path / "backup"
        cm.backup_workspace(workspace, backup_dir)

        # Modify workspace (simulate changes during run)
        (workspace / "original.txt").write_text("modified content")
        (workspace / "new_file.txt").write_text("new file")

        # Restore should bring back original content
        cm.restore_workspace(backup_dir, workspace)

        # Original file should be restored
        assert (workspace / "original.txt").read_text() == "original content"
        # New file should still exist (restore doesn't delete)
        assert (workspace / "new_file.txt").exists()
