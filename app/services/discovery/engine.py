"""
CloudPilot SwitchOps — Infrastructure Discovery Engine

Coordinates filesystem-protected workspace scanning, Terraform HCL parsing,
and Docker Compose YAML parsing to produce a normalized InfrastructureInventory.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from typing import List, Optional

from app.core.errors import ValidationError
from app.domain.inventory import DiscoveredResource, InfrastructureInventory
from app.services.discovery.compose_parser import ComposeParser
from app.services.discovery.terraform_parser import TerraformParser

logger = logging.getLogger("cloudpilot.discovery.engine")

# Security and operational bounds
MAX_WORKSPACE_FILES = 100
MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB

SUPPORTED_TF_EXTENSIONS = {".tf", ".tfvars"}
SUPPORTED_COMPOSE_FILENAMES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}
IGNORED_DIRECTORIES = {".git", ".venv", "venv", "__pycache__", ".terraform", "node_modules"}


class InfrastructureDiscoveryEngine:
    """
    Filesystem-safe discovery engine scanning approved workspace paths,
    enforcing bounds, and assembling normalized infrastructure inventories.
    """

    def __init__(
        self,
        max_files: int = MAX_WORKSPACE_FILES,
        max_file_size_bytes: int = MAX_FILE_SIZE_BYTES,
    ) -> None:
        self.max_files = max_files
        self.max_file_size_bytes = max_file_size_bytes
        self.tf_parser = TerraformParser()
        self.compose_parser = ComposeParser()

    def validate_workspace_path(self, raw_path: str, allowed_base: Optional[Path] = None) -> Path:
        """
        Validate and resolve workspace directory path.
        Rejects directory traversal (e.g. '../') and verifies directory existence.
        """
        target = Path(raw_path).resolve()

        if allowed_base:
            base_resolved = allowed_base.resolve()
            try:
                target.relative_to(base_resolved)
            except ValueError:
                raise ValidationError(
                    f"Path traversal violation: '{raw_path}' escapes allowed root '{allowed_base}'",
                    field="workspace_path",
                )

        if not target.exists():
            raise ValidationError(
                f"Workspace path does not exist: '{raw_path}'",
                field="workspace_path",
            )
        if not target.is_dir():
            raise ValidationError(
                f"Workspace path is not a directory: '{raw_path}'",
                field="workspace_path",
            )

        return target

    def discover(
        self,
        workspace_root: str,
        task_id: Optional[str] = None,
        allowed_base: Optional[Path] = None,
    ) -> InfrastructureInventory:
        """Alias for discover_workspace."""
        return self.discover_workspace(
            workspace_path=workspace_root,
            task_id=task_id,
            allowed_base=allowed_base,
        )

    def discover_workspace(
        self,
        workspace_path: str,
        task_id: Optional[str] = None,
        allowed_base: Optional[Path] = None,
    ) -> InfrastructureInventory:
        """
        Scan workspace directory, parse all supported Terraform and Docker Compose files,
        and assemble an immutable InfrastructureInventory.
        """
        start_time = time.perf_counter()
        root_dir = self.validate_workspace_path(workspace_path, allowed_base=allowed_base)

        discovered_resources: List[DiscoveredResource] = []
        discovered_files: List[str] = []
        file_count = 0

        logger.info("Starting infrastructure discovery in workspace: %s", root_dir)

        # Walk workspace directory safely
        for current_root, dirs, files in os.walk(root_dir, followlinks=False):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

            for filename in files:
                file_count += 1
                if file_count > self.max_files:
                    raise ValidationError(
                        f"Workspace exceeds maximum file limit of {self.max_files} files",
                        field="file_limit",
                    )

                file_path = Path(current_root) / filename

                # Check symlink escapes
                try:
                    resolved_file = file_path.resolve()
                    resolved_file.relative_to(root_dir)
                except (ValueError, RuntimeError):
                    logger.warning("Skipping symlink escaping workspace: %s", file_path)
                    continue

                # Check file size bound
                try:
                    if file_path.stat().st_size > self.max_file_size_bytes:
                        logger.warning("Skipping file exceeding size limit (%s bytes): %s", self.max_file_size_bytes, file_path)
                        continue
                except OSError:
                    continue

                rel_str = str(file_path.relative_to(root_dir)).replace("\\", "/")

                # Parse Terraform HCL files
                if file_path.suffix.lower() in SUPPORTED_TF_EXTENSIONS:
                    tf_resources = self.tf_parser.parse_file(file_path, root_dir)
                    if tf_resources:
                        discovered_resources.extend(tf_resources)
                        discovered_files.append(rel_str)

                # Parse Docker Compose YAML files
                elif filename.lower() in SUPPORTED_COMPOSE_FILENAMES:
                    compose_resources = self.compose_parser.parse_file(file_path, root_dir)
                    if compose_resources:
                        discovered_resources.extend(compose_resources)
                        discovered_files.append(rel_str)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "Discovery completed in %.2fms. Discovered %d resources across %d files.",
            duration_ms,
            len(discovered_resources),
            len(discovered_files),
        )

        return InfrastructureInventory(
            task_id=task_id,
            workspace_root=str(root_dir),
            resources=discovered_resources,
            discovered_files=discovered_files,
            discovery_duration_ms=round(duration_ms, 2),
        )
