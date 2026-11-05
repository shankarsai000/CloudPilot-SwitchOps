"""
CloudPilot SwitchOps — Recovery and Rollback Manager (Phase 4)

Manages file-level backup snapshots, automatic recovery on failure,
restored hash verification, and recovery failure auditing.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cloudpilot.execution.recovery")


class RecoveryManager:
    """
    Guarantees deterministic file recovery in the isolated execution workspace.
    Distinguishes local file restoration from live cloud infrastructure rollback.
    """

    def __init__(self) -> None:
        pass

    def create_pre_execution_snapshot(
        self,
        workspace_path: str,
        relative_file_paths: List[str],
    ) -> Dict[str, str]:
        """
        Creates an immutable local backup snapshot of all files before any mutation.
        Returns: Dict[relative_path, original_sha256]
        """
        snapshot_dir = os.path.join(workspace_path, ".cloudpilot_snapshot")
        os.makedirs(snapshot_dir, exist_ok=True)
        original_hashes: Dict[str, str] = {}

        for rel_path in relative_file_paths:
            clean_rel = os.path.normpath(rel_path).replace("\\", "/")
            src_file = os.path.join(workspace_path, clean_rel)
            if not os.path.isfile(src_file):
                continue

            backup_file = os.path.join(snapshot_dir, clean_rel)
            os.makedirs(os.path.dirname(backup_file), exist_ok=True)
            shutil.copy2(src_file, backup_file)

            with open(backup_file, "rb") as f:
                content = f.read()
            original_hashes[clean_rel] = hashlib.sha256(content).hexdigest()

        logger.info(
            "Created pre-execution snapshot for %d files in '%s'",
            len(original_hashes),
            snapshot_dir,
        )
        return original_hashes

    def rollback_workspace(
        self,
        workspace_path: str,
        expected_before_hashes: Dict[str, str],
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        Restores files from the pre-execution snapshot and verifies restored hashes.
        Returns: (success, restored_files, error_message)
        """
        snapshot_dir = os.path.join(workspace_path, ".cloudpilot_snapshot")
        if not os.path.isdir(snapshot_dir):
            return False, [], "Pre-execution snapshot directory not found; cannot perform file recovery."

        restored_files: List[str] = []
        try:
            for rel_path, expected_hash in expected_before_hashes.items():
                clean_rel = os.path.normpath(rel_path).replace("\\", "/")
                backup_file = os.path.join(snapshot_dir, clean_rel)
                target_file = os.path.join(workspace_path, clean_rel)

                if os.path.isfile(backup_file):
                    shutil.copy2(backup_file, target_file)
                    with open(target_file, "rb") as f:
                        restored_hash = hashlib.sha256(f.read()).hexdigest()

                    # Verify restored hash strictly matches expected before-state
                    if restored_hash != expected_hash:
                        return (
                            False,
                            restored_files,
                            f"Restored file hash mismatch on '{clean_rel}': "
                            f"expected {expected_hash[:16]}, got {restored_hash[:16]}",
                        )
                    restored_files.append(clean_rel)
                elif os.path.isfile(target_file):
                    # File was newly created during execution; delete it to restore before-state
                    os.remove(target_file)
                    restored_files.append(clean_rel)

            logger.info("Successfully rolled back %d files in workspace '%s'", len(restored_files), workspace_path)
            return True, restored_files, None

        except Exception as exc:
            logger.error("File recovery failed with unhandled error: %s", exc)
            return False, restored_files, f"File recovery error: {exc}"
