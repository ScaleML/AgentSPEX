"""Tests for workspace manifest capture and restore."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from harness.checkpoints.workspace_manifest import (
    capture_workspace_manifest, restore_workspace_from_manifest)


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def git_repo(workspace):
    """Create a git repo inside the workspace with a commit and uncommitted change."""
    repo = workspace / "my-project"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo),
        capture_output=True,
    )

    # Create initial file and commit
    (repo / "hello.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo),
        capture_output=True,
    )

    # Make an uncommitted change
    (repo / "hello.py").write_text("print('hello world')\n")

    # Create an untracked file
    (repo / "notes.txt").write_text("some notes\n")

    return repo


class TestCaptureWorkspaceManifest:
    def test_empty_workspace(self, workspace):
        manifest = capture_workspace_manifest(workspace, step_id="1")
        assert manifest["step_id"] == "1"
        assert manifest["git_repos"] == []
        assert manifest["files"] == []
        assert manifest["directories"] == []

    def test_nonexistent_workspace(self, tmp_path):
        manifest = capture_workspace_manifest(tmp_path / "nonexistent", step_id="1")
        assert manifest["git_repos"] == []
        assert manifest["files"] == []

    def test_regular_files(self, workspace):
        (workspace / "data.csv").write_text("a,b,c\n1,2,3\n")
        (workspace / "config.json").write_text('{"key": "value"}')

        manifest = capture_workspace_manifest(workspace, step_id="1")
        assert len(manifest["files"]) == 2

        paths = {f["path"] for f in manifest["files"]}
        assert "data.csv" in paths
        assert "config.json" in paths

        for f in manifest["files"]:
            assert f["content"] is not None
            assert f["size"] > 0

    def test_nested_directories(self, workspace):
        (workspace / "src" / "pkg").mkdir(parents=True)
        (workspace / "src" / "pkg" / "main.py").write_text("# main\n")
        (workspace / "empty_dir").mkdir()

        manifest = capture_workspace_manifest(workspace, step_id="1")
        assert "empty_dir" in manifest["directories"]

        file_paths = {f["path"] for f in manifest["files"]}
        assert os.path.join("src", "pkg", "main.py") in file_paths

    def test_large_file_no_backup_dir(self, workspace):
        """Large file without backup_dir: content=None, no backup_path."""
        large_content = "x" * 2_000_000  # 2MB
        (workspace / "big.txt").write_text(large_content)

        manifest = capture_workspace_manifest(
            workspace, step_id="1", max_file_size=1_000_000
        )
        assert len(manifest["files"]) == 1
        assert manifest["files"][0]["content"] is None
        assert manifest["files"][0]["size"] == 2_000_000
        assert manifest["files"][0].get("backup_path") is None

    def test_large_file_with_backup_dir(self, workspace, tmp_path):
        """Large file with backup_dir: copied to backup, backup_path recorded."""
        large_content = "x" * 2_000_000
        (workspace / "big.txt").write_text(large_content)
        backup_dir = tmp_path / "backup"

        manifest = capture_workspace_manifest(
            workspace,
            step_id="1",
            max_file_size=1_000_000,
            backup_dir=backup_dir,
        )
        assert len(manifest["files"]) == 1
        f = manifest["files"][0]
        assert f["content"] is None
        assert f["backup_path"] is not None
        # Verify the file was actually copied
        assert Path(f["backup_path"]).exists()
        assert Path(f["backup_path"]).read_text() == large_content

    def test_binary_file_no_backup_dir(self, workspace):
        (workspace / "image.bin").write_bytes(b"\x00\x01\x02\xff" * 100)

        manifest = capture_workspace_manifest(workspace, step_id="1")
        assert len(manifest["files"]) == 1
        assert manifest["files"][0]["content"] is None

    def test_binary_file_with_backup_dir(self, workspace, tmp_path):
        """Binary file with backup_dir: copied to backup."""
        binary_data = b"\x00\x01\x02\xff" * 100
        (workspace / "image.bin").write_bytes(binary_data)
        backup_dir = tmp_path / "backup"

        manifest = capture_workspace_manifest(
            workspace,
            step_id="1",
            backup_dir=backup_dir,
        )
        assert len(manifest["files"]) == 1
        f = manifest["files"][0]
        assert f["content"] is None
        assert f["backup_path"] is not None
        assert Path(f["backup_path"]).read_bytes() == binary_data

    def test_ignored_patterns(self, workspace):
        (workspace / "__pycache__").mkdir()
        (workspace / "__pycache__" / "mod.pyc").write_bytes(b"bytecode")
        (workspace / "real.txt").write_text("real content")

        manifest = capture_workspace_manifest(workspace, step_id="1")
        file_paths = {f["path"] for f in manifest["files"]}
        assert "real.txt" in file_paths
        assert "__pycache__" not in file_paths

    def test_git_repo_capture(self, workspace, git_repo):
        manifest = capture_workspace_manifest(workspace, step_id="2")
        assert len(manifest["git_repos"]) == 1

        repo = manifest["git_repos"][0]
        assert repo["path"] == "my-project"
        assert repo["commit"] is not None
        assert len(repo["commit"]) == 40  # full SHA
        assert repo["diff"] is not None
        assert "hello world" in repo["diff"]
        assert "notes.txt" in repo["untracked_files"]
        assert repo["untracked_files"]["notes.txt"] == "some notes\n"

    def test_git_repo_no_remote(self, workspace):
        """Repo without a remote should still be captured (remote_url=None)."""
        repo = workspace / "local-repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(repo),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(repo),
            capture_output=True,
        )
        (repo / "f.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo),
            capture_output=True,
        )

        manifest = capture_workspace_manifest(workspace, step_id="1")
        assert len(manifest["git_repos"]) == 1
        assert manifest["git_repos"][0]["remote_url"] is None


class TestRestoreWorkspaceFromManifest:
    def test_restore_regular_files(self, tmp_path):
        target = tmp_path / "restored"
        manifest = {
            "step_id": "1",
            "timestamp": "2026-01-01T00:00:00",
            "git_repos": [],
            "files": [
                {"path": "data.csv", "content": "a,b,c\n1,2,3\n", "size": 12},
                {
                    "path": os.path.join("sub", "config.json"),
                    "content": '{"k":1}',
                    "size": 6,
                },
            ],
            "directories": ["empty_dir"],
        }
        result = restore_workspace_from_manifest(manifest, target)
        assert result is True
        assert (target / "data.csv").read_text() == "a,b,c\n1,2,3\n"
        assert (target / "sub" / "config.json").read_text() == '{"k":1}'
        assert (target / "empty_dir").is_dir()

    def test_restore_skips_null_content_no_backup(self, tmp_path):
        target = tmp_path / "restored"
        manifest = {
            "step_id": "1",
            "timestamp": "2026-01-01T00:00:00",
            "git_repos": [],
            "files": [
                {"path": "big.bin", "content": None, "size": 999999},
            ],
            "directories": [],
        }
        logs = []
        result = restore_workspace_from_manifest(manifest, target, logger=logs.append)
        assert result is True  # no backup_path either → just skip
        assert not (target / "big.bin").exists()
        assert any(
            "no saved content" in msg.lower() or "no backup" in msg.lower()
            for msg in logs
        )

    def test_restore_from_backup_path(self, tmp_path):
        """File with backup_path should be restored from the backup."""
        # Prepare a backup file
        backup_dir = tmp_path / "backup"
        backup_file = backup_dir / "workspace_files" / "data.bin"
        backup_file.parent.mkdir(parents=True)
        backup_file.write_bytes(b"\x00\x01\x02" * 1000)

        target = tmp_path / "restored"
        manifest = {
            "step_id": "1",
            "timestamp": "2026-01-01T00:00:00",
            "git_repos": [],
            "files": [
                {
                    "path": "data.bin",
                    "content": None,
                    "size": 3000,
                    "backup_path": str(backup_file),
                },
            ],
            "directories": [],
        }
        result = restore_workspace_from_manifest(manifest, target)
        assert result is True
        assert (target / "data.bin").exists()
        assert (target / "data.bin").read_bytes() == b"\x00\x01\x02" * 1000

    def test_restore_missing_remote_skips_repo(self, tmp_path):
        target = tmp_path / "restored"
        manifest = {
            "step_id": "1",
            "timestamp": "2026-01-01T00:00:00",
            "git_repos": [
                {
                    "path": "broken",
                    "remote_url": None,
                    "branch": "main",
                    "commit": "abc123",
                    "diff": None,
                    "untracked_files": {},
                }
            ],
            "files": [],
            "directories": [],
        }
        logs = []
        result = restore_workspace_from_manifest(manifest, target, logger=logs.append)
        assert result is False
        assert any("skipping repo" in msg.lower() for msg in logs)


class TestRoundTrip:
    """Test capture → restore roundtrip for regular files."""

    def test_files_roundtrip(self, workspace, tmp_path):
        # Setup files
        (workspace / "readme.md").write_text("# Hello\n")
        (workspace / "src").mkdir()
        (workspace / "src" / "app.py").write_text("import os\n")
        (workspace / "empty").mkdir()

        # Capture
        manifest = capture_workspace_manifest(workspace, step_id="5")

        # Restore to a new location
        target = tmp_path / "restored"
        result = restore_workspace_from_manifest(manifest, target)
        assert result is True

        assert (target / "readme.md").read_text() == "# Hello\n"
        assert (target / "src" / "app.py").read_text() == "import os\n"
        assert (target / "empty").is_dir()

    def test_large_and_small_files_roundtrip(self, workspace, tmp_path):
        """Roundtrip with both inline (small) and backup (large/binary) files."""
        backup_dir = tmp_path / "backup"

        # Small text file (inline)
        (workspace / "small.txt").write_text("hello\n")
        # Large text file (backup)
        (workspace / "large.csv").write_text("x" * 2_000_000)
        # Binary file (backup)
        (workspace / "model.bin").write_bytes(b"\x00\xff" * 500)

        manifest = capture_workspace_manifest(
            workspace,
            step_id="7",
            max_file_size=1_000_000,
            backup_dir=backup_dir,
        )

        # Verify manifest structure
        by_path = {f["path"]: f for f in manifest["files"]}
        assert by_path["small.txt"]["content"] == "hello\n"
        assert by_path["large.csv"]["content"] is None
        assert by_path["large.csv"]["backup_path"] is not None
        assert by_path["model.bin"]["content"] is None
        assert by_path["model.bin"]["backup_path"] is not None

        # Restore
        target = tmp_path / "restored"
        result = restore_workspace_from_manifest(manifest, target)
        assert result is True
        assert (target / "small.txt").read_text() == "hello\n"
        assert (target / "large.csv").read_text() == "x" * 2_000_000
        assert (target / "model.bin").read_bytes() == b"\x00\xff" * 500

    def test_git_repo_roundtrip(self, workspace, git_repo, tmp_path):
        """Capture a git repo and restore it to a new directory.

        Since the repo has no remote, we can't clone it.  Instead we verify
        that the manifest correctly captured the state.
        """
        manifest = capture_workspace_manifest(workspace, step_id="3")
        assert len(manifest["git_repos"]) == 1

        repo_info = manifest["git_repos"][0]
        assert repo_info["commit"] is not None
        assert repo_info["diff"] is not None
        assert "notes.txt" in repo_info["untracked_files"]

    def test_git_untracked_binary_backup(self, workspace, git_repo, tmp_path):
        """Binary untracked file in git repo should be backed up."""
        backup_dir = tmp_path / "backup"
        binary_data = b"\x00\x01\x02\xff" * 200
        (git_repo / "model.bin").write_bytes(binary_data)

        manifest = capture_workspace_manifest(
            workspace,
            step_id="8",
            backup_dir=backup_dir,
        )
        repo = manifest["git_repos"][0]
        assert repo["untracked_files"]["model.bin"] is None
        assert "model.bin" in repo["untracked_backup_paths"]
        bk_path = repo["untracked_backup_paths"]["model.bin"]
        assert Path(bk_path).read_bytes() == binary_data
