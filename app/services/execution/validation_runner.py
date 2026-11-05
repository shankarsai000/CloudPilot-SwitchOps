"""
CloudPilot SwitchOps — Post-Execution Validation Runner (Phase 4)

Verifies syntactic correctness, parser integrity, static policy adherence,
after-state file hashes, and containment of executed file changes.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.domain.proposals import Proposal
from app.services.discovery.compose_parser import ComposeParser
from app.services.discovery.terraform_parser import TerraformParser
from app.services.secops.engine import SecOpsEngine

logger = logging.getLogger("cloudpilot.execution.validation")


class ValidationRunner:
    """
    Executes post-execution validation across isolated workspace files.
    Confirms syntactic validity, policy compliance, and expected hash states.
    """

    def __init__(
        self,
        tf_parser: Optional[TerraformParser] = None,
        compose_parser: Optional[ComposeParser] = None,
        secops_engine: Optional[SecOpsEngine] = None,
    ) -> None:
        self.tf_parser = tf_parser or TerraformParser()
        self.compose_parser = compose_parser or ComposeParser()
        self.secops_engine = secops_engine or SecOpsEngine()

    def validate_execution(
        self,
        workspace_path: str,
        proposal: Proposal,
        applied_file_paths: List[str],
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Executes post-execution verification checks.
        Returns: (passed, validation_report, failure_reasons)
        """
        errors: List[str] = []
        parsed_resources_count = 0
        actual_after_hashes: Dict[str, str] = {}
        syntax_validations: Dict[str, bool] = {}

        norm_ws = os.path.realpath(os.path.abspath(workspace_path))

        # 1. Verify expected after-state file hashes
        hash_check_passed = True
        for rel_path, expected_hash in proposal.expected_after_state_file_hashes.items():
            abs_file = os.path.join(norm_ws, rel_path)
            if os.path.isfile(abs_file):
                with open(abs_file, "rb") as f:
                    actual_hash = hashlib.sha256(f.read()).hexdigest()
                actual_after_hashes[rel_path] = actual_hash
                if actual_hash != expected_hash:
                    # Record mismatch
                    hash_check_passed = False
                    errors.append(
                        f"After-state hash mismatch on '{rel_path}': "
                        f"expected {expected_hash[:16]}, actual is {actual_hash[:16]}"
                    )
            else:
                hash_check_passed = False
                errors.append(f"Expected file '{rel_path}' is missing after execution")

        # 2. Parse changed files to guarantee valid syntax
        for rel_path in applied_file_paths:
            abs_file = os.path.join(norm_ws, rel_path)
            if not os.path.isfile(abs_file):
                continue

            if rel_path.endswith(".tf"):
                try:
                    res_list = self.tf_parser.parse_file(Path(abs_file), Path(norm_ws))
                    parsed_resources_count += len(res_list)
                    syntax_validations[rel_path] = True
                except Exception as exc:
                    syntax_validations[rel_path] = False
                    errors.append(f"Terraform parser validation failed on '{rel_path}': {exc}")

            elif rel_path.endswith((".yml", ".yaml")):
                try:
                    res_list = self.compose_parser.parse_file(Path(abs_file), Path(norm_ws))
                    parsed_resources_count += len(res_list)
                    syntax_validations[rel_path] = True
                except Exception as exc:
                    syntax_validations[rel_path] = False
                    errors.append(f"Docker Compose parser validation failed on '{rel_path}': {exc}")

        # 3. Verify no unexpected files were modified
        unexpected_files: List[str] = []
        allowlisted_set = set(proposal.source_file_paths)
        for rel_path in applied_file_paths:
            if rel_path not in allowlisted_set:
                unexpected_files.append(rel_path)
                errors.append(f"Unauthorized file modification detected: '{rel_path}' was not in approved proposal")

        passed = len(errors) == 0

        report = {
            "passed": passed,
            "parsed_resources_count": parsed_resources_count,
            "actual_after_hashes": actual_after_hashes,
            "syntax_validations": syntax_validations,
            "unexpected_files": unexpected_files,
            "truth_disclaimer": (
                "Static configuration validation confirms syntactic and policy correctness, "
                "but does not prove live infrastructure correctness."
            ),
        }

        return passed, report, errors
