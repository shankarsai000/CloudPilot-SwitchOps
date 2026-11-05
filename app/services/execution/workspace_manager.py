"""
CloudPilot SwitchOps — Workspace Manager (Phase 4)

Provides isolated, sandboxed execution workspaces.
Enforces strict file allowlisting, path traversal rejection, symlink escape detection,
maximum file size limits, and containment within authorized directories.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import shutil
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cloudpilot.execution.workspace")

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_FILES_PER_WORKSPACE = 100


class WorkspaceSecurityError(Exception):
    """Raised when an operation violates workspace containment or security boundaries."""


class WorkspaceManager:
    """
    Manages isolated execution directories for safe configuration mutations.
    Guarantees no modifications occur directly in the original workspace.
    """

    def __init__(self, base_workspaces_dir: Optional[str] = None) -> None:
        if base_workspaces_dir:
            self.base_dir = os.path.abspath(base_workspaces_dir)
        else:
            self.base_dir = os.path.abspath(os.path.join(os.getcwd(), ".cloudpilot", "workspaces"))
        os.makedirs(self.base_dir, exist_ok=True)

    def create_isolated_workspace(
        self,
        execution_id: str,
        source_root: str,
        allowlisted_relative_paths: List[str],
    ) -> Tuple[str, Dict[str, str]]:
        """
        Creates a sandboxed workspace and copies only allowlisted files from source_root.
        Computes and records original file SHA-256 hashes.
        Returns: (isolated_workspace_path, recorded_file_hashes)
        """
        source_norm = os.path.realpath(os.path.abspath(source_root))
        if not os.path.exists(source_norm):
            raise WorkspaceSecurityError(f"Source workspace root does not exist: {source_root}")

        if len(allowlisted_relative_paths) > MAX_FILES_PER_WORKSPACE:
            raise WorkspaceSecurityError(
                f"Too many allowlisted files ({len(allowlisted_relative_paths)} > {MAX_FILES_PER_WORKSPACE})"
            )

        # Isolated directory for this execution
        ws_path = os.path.realpath(os.path.abspath(os.path.join(self.base_dir, execution_id)))
        # Prevent traversal in execution_id
        if not ws_path.startswith(self.base_dir):
            raise WorkspaceSecurityError(f"Security error: Invalid execution workspace path '{ws_path}'")

        if os.path.exists(ws_path):
            shutil.rmtree(ws_path, ignore_errors=True)
        os.makedirs(ws_path, exist_ok=True)

        recorded_hashes: Dict[str, str] = {}

        for rel_path in allowlisted_relative_paths:
            # Prevent path traversal in relative path
            clean_rel = os.path.normpath(rel_path).replace("\\", "/")
            if clean_rel.startswith("../") or clean_rel.startswith("..\\") or clean_rel == "..":
                raise WorkspaceSecurityError(f"Path traversal detected in allowlisted path '{rel_path}'")

            src_file = os.path.realpath(os.path.join(source_norm, clean_rel))

            # Detect symlink escapes or escaping source_root
            if not src_file.startswith(source_norm):
                raise WorkspaceSecurityError(f"Symlink or path escape detected for '{rel_path}'")

            if not os.path.isfile(src_file):
                logger.warning("Allowlisted file '%s' does not exist in source workspace; skipping copy", clean_rel)
                continue

            # Check file size limit
            file_size = os.path.getsize(src_file)
            if file_size > MAX_FILE_SIZE_BYTES:
                raise WorkspaceSecurityError(
                    f"File '{clean_rel}' exceeds maximum permitted size ({file_size} > {MAX_FILE_SIZE_BYTES} bytes)"
                )

            dest_file = os.path.realpath(os.path.join(ws_path, clean_rel))
            if not dest_file.startswith(ws_path):
                raise WorkspaceSecurityError(f"Destination path escape detected for '{dest_file}'")

            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            shutil.copy2(src_file, dest_file)

            with open(dest_file, "rb") as f:
                content = f.read()
            recorded_hashes[clean_rel] = hashlib.sha256(content).hexdigest()

        logger.info(
            "Created isolated workspace '%s' with %d allowlisted files",
            ws_path,
            len(recorded_hashes),
        )
        return ws_path, recorded_hashes

    def resolve_contained_path(self, workspace_path: str, relative_path: str) -> str:
        """
        Safely resolves a relative path within a workspace, guaranteeing no traversal.
        """
        norm_ws = os.path.realpath(os.path.abspath(workspace_path))
        clean_rel = os.path.normpath(relative_path).replace("\\", "/")
        if clean_rel.startswith("../") or clean_rel.startswith("..\\") or clean_rel == "..":
            raise WorkspaceSecurityError(f"Path traversal forbidden: '{relative_path}'")

        resolved = os.path.realpath(os.path.join(norm_ws, clean_rel))
        if not resolved.startswith(norm_ws):
            raise WorkspaceSecurityError(f"Path escape outside workspace: '{relative_path}' -> '{resolved}'")

        return resolved

    def cleanup_workspace(self, workspace_path: str) -> None:
        """Removes the isolated workspace directory."""
        norm_ws = os.path.realpath(os.path.abspath(workspace_path))
        if norm_ws.startswith(self.base_dir) and os.path.exists(norm_ws):
            try:
                shutil.rmtree(norm_ws, ignore_errors=True)
                logger.info("Cleaned up isolated workspace '%s'", norm_ws)
            except Exception as exc:
                logger.warning("Failed to clean up workspace '%s': %s", norm_ws, exc)
