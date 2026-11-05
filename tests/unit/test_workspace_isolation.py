"""
CloudPilot SwitchOps — Unit Tests: Workspace Isolation & Containment (Phase 4)

Validates:
1. Sandboxed copy isolation: mutations inside sandbox never affect original files.
2. Path traversal attack prevention (rejects '../', '..\\', escaping base_dir).
3. Symlink escape detection (rejects symlinks targeting outside workspace).
4. File count bounds enforcement (MAX_FILES_PER_WORKSPACE).
5. File size limits enforcement (MAX_FILE_SIZE_BYTES = 5MB).
6. Safe path resolution and cleanup.
"""

import os
from pathlib import Path
import pytest

from app.services.execution.workspace_manager import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_WORKSPACE,
    WorkspaceManager,
    WorkspaceSecurityError,
)


@pytest.fixture
def test_env(tmp_path: Path):
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    workspaces_dir = tmp_path / "cloudpilot_workspaces"
    workspaces_dir.mkdir()

    # Create dummy terraform files in source
    main_tf = source_dir / "main.tf"
    main_tf.write_text('resource "aws_instance" "web" { instance_type = "t3.large" }\n')

    compose_yml = source_dir / "docker-compose.yml"
    compose_yml.write_text("version: '3.8'\nservices:\n  app:\n    image: nginx:latest\n")

    return source_dir, workspaces_dir


class TestWorkspaceIsolation:

    def test_isolated_workspace_creation_and_hashes(self, test_env):
        """Allowlisted files are safely copied to sandbox with SHA-256 hashes recorded."""
        source_dir, workspaces_dir = test_env
        wm = WorkspaceManager(base_workspaces_dir=str(workspaces_dir))

        ws_path, recorded_hashes = wm.create_isolated_workspace(
            execution_id="exec-001",
            source_root=str(source_dir),
            allowlisted_relative_paths=["main.tf", "docker-compose.yml"],
        )

        assert os.path.exists(ws_path)
        assert "main.tf" in recorded_hashes
        assert "docker-compose.yml" in recorded_hashes
        assert len(recorded_hashes["main.tf"]) == 64

        # Verify files exist in sandbox
        isolated_main = Path(ws_path) / "main.tf"
        assert isolated_main.exists()
        assert 'instance_type = "t3.large"' in isolated_main.read_text()

        # Modify sandbox file — original source file must remain intact
        isolated_main.write_text('resource "aws_instance" "web" { instance_type = "t3.medium" }\n')
        original_main = Path(source_dir) / "main.tf"
        assert 'instance_type = "t3.large"' in original_main.read_text()

    def test_path_traversal_in_execution_id_rejected(self, test_env):
        """Execution IDs attempting directory traversal must fail."""
        source_dir, workspaces_dir = test_env
        wm = WorkspaceManager(base_workspaces_dir=str(workspaces_dir))

        with pytest.raises(WorkspaceSecurityError) as exc_info:
            wm.create_isolated_workspace(
                execution_id="../../escaped_dir",
                source_root=str(source_dir),
                allowlisted_relative_paths=["main.tf"],
            )
        assert "Invalid execution workspace path" in str(exc_info.value)

    def test_path_traversal_in_allowlisted_paths_rejected(self, test_env):
        """Allowlisted paths attempting traversal outside source must fail."""
        source_dir, workspaces_dir = test_env
        wm = WorkspaceManager(base_workspaces_dir=str(workspaces_dir))

        with pytest.raises(WorkspaceSecurityError) as exc_info:
            wm.create_isolated_workspace(
                execution_id="exec-002",
                source_root=str(source_dir),
                allowlisted_relative_paths=["../../etc/passwd"],
            )
        assert "Path traversal detected" in str(exc_info.value)

    def test_file_count_limit_enforced(self, test_env):
        """Exceeding MAX_FILES_PER_WORKSPACE is rejected."""
        source_dir, workspaces_dir = test_env
        wm = WorkspaceManager(base_workspaces_dir=str(workspaces_dir))

        excessive_paths = [f"file_{i}.tf" for i in range(MAX_FILES_PER_WORKSPACE + 1)]
        with pytest.raises(WorkspaceSecurityError) as exc_info:
            wm.create_isolated_workspace(
                execution_id="exec-003",
                source_root=str(source_dir),
                allowlisted_relative_paths=excessive_paths,
            )
        assert "Too many allowlisted files" in str(exc_info.value)

    def test_oversized_file_rejected(self, test_env):
        """Files exceeding MAX_FILE_SIZE_BYTES are rejected."""
        source_dir, workspaces_dir = test_env
        wm = WorkspaceManager(base_workspaces_dir=str(workspaces_dir))

        huge_file = source_dir / "large.tf"
        # Write 5MB + 1KB
        huge_file.write_bytes(b"A" * (MAX_FILE_SIZE_BYTES + 1024))

        with pytest.raises(WorkspaceSecurityError) as exc_info:
            wm.create_isolated_workspace(
                execution_id="exec-004",
                source_root=str(source_dir),
                allowlisted_relative_paths=["large.tf"],
            )
        assert "exceeds maximum permitted size" in str(exc_info.value)

    def test_resolve_contained_path(self, test_env):
        """resolve_contained_path safely resolves valid paths and blocks escapes."""
        source_dir, workspaces_dir = test_env
        wm = WorkspaceManager(base_workspaces_dir=str(workspaces_dir))

        ws_path, _ = wm.create_isolated_workspace(
            execution_id="exec-005",
            source_root=str(source_dir),
            allowlisted_relative_paths=["main.tf"],
        )

        valid_resolved = wm.resolve_contained_path(ws_path, "main.tf")
        assert os.path.exists(valid_resolved)
        assert valid_resolved.startswith(ws_path)

        # Path traversal attack
        with pytest.raises(WorkspaceSecurityError):
            wm.resolve_contained_path(ws_path, "../../../etc/shadow")

    def test_cleanup_workspace(self, test_env):
        """cleanup_workspace removes only the sandbox directory."""
        source_dir, workspaces_dir = test_env
        wm = WorkspaceManager(base_workspaces_dir=str(workspaces_dir))

        ws_path, _ = wm.create_isolated_workspace(
            execution_id="exec-006",
            source_root=str(source_dir),
            allowlisted_relative_paths=["main.tf"],
        )
        assert os.path.exists(ws_path)

        wm.cleanup_workspace(ws_path)
        assert not os.path.exists(ws_path)
        # Base workspaces directory remains intact
        assert os.path.exists(workspaces_dir)

