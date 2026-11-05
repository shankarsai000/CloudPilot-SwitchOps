"""
CloudPilot SwitchOps — Filesystem Containment & Isolation Adversarial Tests (Phase 4.1)

Validates Workstream C (Filesystem Isolation and Sandbox Boundaries):
1. Relative path traversal (../) cannot escape workspace root.
2. Absolute path parameters cannot escape workspace root.
3. Symlink creation, modification, or dereference to host filesystem is strictly blocked.
4. Workspace creation strictly confined to designated workspace base directory.
5. Non-infrastructure files (.py, .sh, .bashrc, /etc/passwd, .env) cannot be modified.
6. Execution ID cannot contain path traversal sequences.
7. Hard link unlinking ensures copy-on-write isolation (no mutating through hardlinks).
8. Workspace cleanup refuses to delete parent directories or base workspace root.
9. Attempted write to unapproved file is rejected.
"""

import os
from pathlib import Path
import pytest

from app.domain.candidates import ProposedChange
from app.services.execution.change_applier import ChangeApplier, ChangeApplicationError
from app.services.execution.workspace_manager import (
    WorkspaceManager,
    WorkspaceSecurityError,
    MAX_FILE_SIZE_BYTES,
)


@pytest.fixture
def workspace_fixture(tmp_path: Path):
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    base_ws_dir = tmp_path / "workspaces"
    base_ws_dir.mkdir()

    # Valid config files
    tf_file = source_dir / "main.tf"
    tf_file.write_bytes(b'resource "aws_instance" "web" {\n  instance_type = "t3.large"\n}\n')

    compose_file = source_dir / "docker-compose.yml"
    compose_file.write_bytes(b'version: "3.8"\nservices:\n  app:\n    image: nginx:alpine\n')

    ws_mgr = WorkspaceManager(base_workspaces_dir=str(base_ws_dir))
    applier = ChangeApplier()

    return {
        "source_dir": source_dir,
        "base_ws_dir": base_ws_dir,
        "ws_mgr": ws_mgr,
        "applier": applier,
        "tf_file": tf_file,
        "compose_file": compose_file,
    }


class TestFilesystemContainmentAdversarial:

    def test_path_traversal_dot_dot_rejected(self, workspace_fixture):
        """Relative paths with ../ are detected and rejected immediately."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        source_dir = env["source_dir"]

        traversal_attempts = [
            "../../etc/passwd",
            "../secret.tf",
            "subdir/../../outside.tf",
            "..\\windows\\system32\\cmd.exe",
            "sub\\..\\..\\evil.tf",
        ]

        for bad_path in traversal_attempts:
            with pytest.raises(WorkspaceSecurityError) as exc_info:
                ws_mgr.create_isolated_workspace(
                    execution_id="exec-traversal-001",
                    source_root=str(source_dir),
                    allowlisted_relative_paths=[bad_path],
                )
            assert "traversal" in exc_info.value.args[0].lower() or "security" in exc_info.value.args[0].lower()

    def test_absolute_path_injection_rejected(self, workspace_fixture):
        """Absolute paths (/etc/passwd, C:/...) cannot escape workspace root."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        source_dir = env["source_dir"]

        abs_attempts = [
            "/etc/passwd",
            "/var/log/syslog",
            "C:/Windows/win.ini",
            "\\Windows\\System32\\config\\SAM",
        ]

        for abs_path in abs_attempts:
            with pytest.raises(WorkspaceSecurityError) as exc_info:
                ws_mgr.create_isolated_workspace(
                    execution_id="exec-abs-001",
                    source_root=str(source_dir),
                    allowlisted_relative_paths=[abs_path],
                )
            assert "absolute" in exc_info.value.args[0].lower() or "traversal" in exc_info.value.args[0].lower()

    def test_execution_id_traversal_rejected(self, workspace_fixture):
        """execution_id containing path traversal or invalid characters is blocked."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        source_dir = env["source_dir"]

        bad_exec_ids = [
            "../../outside",
            "exec-../escape",
            "exec/escape",
            "exec-`whoami`",
            "exec-$;rm -rf",
            "exec-\x00nullbyte",
            "invalid_prefix_001",
        ]

        for bad_id in bad_exec_ids:
            with pytest.raises(WorkspaceSecurityError) as exc_info:
                ws_mgr.create_isolated_workspace(
                    execution_id=bad_id,
                    source_root=str(source_dir),
                    allowlisted_relative_paths=["main.tf"],
                )
            assert "invalid execution" in exc_info.value.args[0].lower() or "security" in exc_info.value.args[0].lower()

    def test_symlink_file_in_source_rejected(self, workspace_fixture, tmp_path):
        """A symlink pointing to an external file must be rejected to prevent exfiltration."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        source_dir = env["source_dir"]

        # Target external secret file
        secret_file = tmp_path / "external_secret.tf"
        secret_file.write_bytes(b'secret_key = "sensitive-token-1234"\n')

        symlink_file = source_dir / "symlink_test.tf"
        try:
            os.symlink(str(secret_file), str(symlink_file))
        except OSError:
            # On Windows without developer mode/admin privileges, symlink creation might raise OSError
            pytest.skip("Symlink creation requires elevated permissions on this OS")

        with pytest.raises(WorkspaceSecurityError) as exc_info:
            ws_mgr.create_isolated_workspace(
                execution_id="exec-symlink-001",
                source_root=str(source_dir),
                allowlisted_relative_paths=["symlink_test.tf"],
            )
        assert "symlink" in exc_info.value.args[0].lower()

    def test_prohibited_extensions_rejected(self, workspace_fixture):
        """Non-infrastructure files (.py, .sh, .bashrc, .env, .exe) cannot be allowlisted."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        source_dir = env["source_dir"]

        # Create disallowed files in source
        prohibited = [
            ("script.sh", b"#!/bin/bash\nrm -rf /\n"),
            ("exploit.py", b"import os; os.system('echo pwned')\n"),
            (".bashrc", b"alias ls='echo pwned'\n"),
            (".env", b"DB_PASS=secret123\n"),
            ("payload.exe", b"MZbinaryexecutable\n"),
        ]

        for fname, content in prohibited:
            fpath = source_dir / fname
            fpath.write_bytes(content)

            with pytest.raises(WorkspaceSecurityError) as exc_info:
                ws_mgr.create_isolated_workspace(
                    execution_id="exec-ext-001",
                    source_root=str(source_dir),
                    allowlisted_relative_paths=[fname],
                )
            assert "prohibited file type" in exc_info.value.args[0].lower()

    def test_max_file_size_enforced(self, workspace_fixture):
        """Files exceeding MAX_FILE_SIZE_BYTES cannot be staged into isolated workspace."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        source_dir = env["source_dir"]

        huge_file = source_dir / "huge.tf"
        # Write 5MB + 1 byte
        huge_file.write_bytes(b"#" * (MAX_FILE_SIZE_BYTES + 1))

        with pytest.raises(WorkspaceSecurityError) as exc_info:
            ws_mgr.create_isolated_workspace(
                execution_id="exec-huge-001",
                source_root=str(source_dir),
                allowlisted_relative_paths=["huge.tf"],
            )
        assert "exceeds maximum permitted size" in exc_info.value.args[0].lower()

    def test_max_files_limit_enforced(self, workspace_fixture):
        """Workspaces requesting more than MAX_FILES_PER_WORKSPACE are rejected."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        source_dir = env["source_dir"]

        too_many = [f"file_{i}.tf" for i in range(101)]
        with pytest.raises(WorkspaceSecurityError) as exc_info:
            ws_mgr.create_isolated_workspace(
                execution_id="exec-many-001",
                source_root=str(source_dir),
                allowlisted_relative_paths=too_many,
            )
        assert "too many allowlisted files" in exc_info.value.args[0].lower()

    def test_change_applier_path_traversal_rejected(self, workspace_fixture):
        """ChangeApplier rejects changes targeting paths outside workspace."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        applier: ChangeApplier = env["applier"]
        source_dir = env["source_dir"]

        ws_path, _ = ws_mgr.create_isolated_workspace(
            execution_id="exec-applier-001",
            source_root=str(source_dir),
            allowlisted_relative_paths=["main.tf"],
        )

        malicious_change = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="../../etc/passwd",
        )

        with pytest.raises(ChangeApplicationError) as exc_info:
            applier.apply_changes(ws_path, [malicious_change])
        assert "traversal" in exc_info.value.args[0].lower() or "outside workspace" in exc_info.value.args[0].lower()

    def test_change_applier_prohibited_extension_rejected(self, workspace_fixture):
        """ChangeApplier rejects changes targeting non-permitted file extensions."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        applier: ChangeApplier = env["applier"]
        source_dir = env["source_dir"]

        ws_path, _ = ws_mgr.create_isolated_workspace(
            execution_id="exec-applier-002",
            source_root=str(source_dir),
            allowlisted_relative_paths=["main.tf"],
        )

        malicious_change = ProposedChange(
            action_type="MODIFY",
            resource_type="shell_script",
            resource_id="script.sh",
            resource_name="script",
            attribute_path="content",
            current_value="echo 1",
            proposed_value="rm -rf /",
            source_file="deploy.sh",
        )

        with pytest.raises(ChangeApplicationError) as exc_info:
            applier.apply_changes(ws_path, [malicious_change])
        assert "prohibited file type" in exc_info.value.args[0].lower()

    def test_change_applier_breaks_hard_links(self, workspace_fixture, tmp_path):
        """Writing to a hard-linked file unlinks it first so the target file is not mutated in place."""
        env = workspace_fixture
        applier: ChangeApplier = env["applier"]

        # Create a test file and a hard link to simulate copy-on-write integrity
        ws_dir = tmp_path / "hardlink_ws"
        ws_dir.mkdir()
        original_file = ws_dir / "main.tf"
        original_file.write_bytes(b'resource "aws_instance" "web" {\n  instance_type = "t3.large"\n}\n')

        link_target = tmp_path / "linked_source.tf"
        try:
            os.link(str(original_file), str(link_target))
        except (OSError, AttributeError):
            pytest.skip("Hard links not supported or lack privileges on this filesystem")

        # Verify st_nlink == 2 initially
        assert os.stat(original_file).st_nlink == 2

        change = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )

        # Apply change
        applier.apply_changes(str(ws_dir), [change])

        # Verify that original_file was unlinked and re-created:
        # 1. ws_dir/main.tf now has proposed value
        assert "t3.medium" in original_file.read_text()
        # 2. linked_source.tf STILL HAS the OLD value (not modified through hard link)
        assert "t3.large" in link_target.read_text()
        # 3. ws_dir/main.tf st_nlink is now 1
        assert os.stat(original_file).st_nlink == 1

    def test_cleanup_refuses_outside_base_dir(self, workspace_fixture, tmp_path):
        """cleanup_workspace rejects deleting parent directories or directories outside base_dir."""
        env = workspace_fixture
        ws_mgr: WorkspaceManager = env["ws_mgr"]
        base_ws_dir = env["base_ws_dir"]

        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()

        # Attempt to clean up outside dir
        with pytest.raises(WorkspaceSecurityError) as exc_info:
            ws_mgr.cleanup_workspace(str(outside_dir))
        assert "outside workspaces base directory" in exc_info.value.args[0].lower() or "rejected" in exc_info.value.args[0].lower()

        # Attempt to clean up the base_dir itself
        with pytest.raises(WorkspaceSecurityError) as exc_info:
            ws_mgr.cleanup_workspace(str(base_ws_dir))
        assert "outside workspaces base directory" in exc_info.value.args[0].lower() or "rejected" in exc_info.value.args[0].lower()
