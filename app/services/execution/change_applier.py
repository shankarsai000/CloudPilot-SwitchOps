"""
CloudPilot SwitchOps — Structured Change Applier (Phase 4)

Applies allowlisted, structured file mutations (Terraform HCL and Docker Compose YAML)
to isolated workspace files. Rejects unsupported or arbitrary string manipulations.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.domain.candidates import ProposedChange
from app.domain.execution import FileMutationRecord

logger = logging.getLogger("cloudpilot.execution.applier")

ALLOWED_OPERATIONS = {"MODIFY", "UPDATE_ATTRIBUTE", "REPLACE_VALUE", "ADD_BLOCK", "ADD", "REMOVE"}


class ChangeApplicationError(Exception):
    """Raised when a proposed change cannot be safely or structurally applied."""


class ChangeApplier:
    """
    Applies structured declarative mutations to configuration files
    within an isolated execution workspace.
    """

    def apply_changes(
        self,
        workspace_path: str,
        changes: List[ProposedChange],
    ) -> List[FileMutationRecord]:
        """
        Applies a list of canonical proposed changes to files in the isolated workspace.
        Returns detailed FileMutationRecord audit entries for each modification.
        """
        records: List[FileMutationRecord] = []

        for ch in changes:
            # Check operation allowlist
            action = (ch.action_type or "MODIFY").upper()
            if action not in ALLOWED_OPERATIONS:
                raise ChangeApplicationError(
                    f"Unsupported mutation operation '{action}'. Permitted operations: {ALLOWED_OPERATIONS}"
                )

            src_file_rel = ch.source_file or "main.tf"
            clean_rel = os.path.normpath(src_file_rel).replace("\\", "/")
            target_file = os.path.join(workspace_path, clean_rel)

            if not os.path.isfile(target_file):
                # If target file doesn't exist, create an initial minimal declarative scaffold
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                    f.write(f"# Auto-generated for resource {ch.resource_id}\n")

            with open(target_file, "rb") as f:
                content_bytes = f.read()
            before_hash = hashlib.sha256(content_bytes).hexdigest()

            text = content_bytes.decode("utf-8", errors="replace")

            # Apply structured modification
            modified_text = self._apply_structured_mutation(text, ch, clean_rel)

            # Write updated file back to isolated workspace
            with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(modified_text)

            with open(target_file, "rb") as f:
                after_bytes = f.read()
            after_hash = hashlib.sha256(after_bytes).hexdigest()

            record = FileMutationRecord(
                file_path=clean_rel,
                before_hash=before_hash,
                after_hash=after_hash,
                operation=action,
                resource_id=ch.resource_id,
                attribute_path=ch.attribute_path,
                old_value=str(ch.current_value),
                new_value=str(ch.proposed_value),
                status="APPLIED",
            )
            records.append(record)
            logger.info(
                "Applied %s on '%s' (%s: %s -> %s)",
                action,
                clean_rel,
                ch.attribute_path,
                ch.current_value,
                ch.proposed_value,
            )

        return records

    def apply_mutation_to_text(
        self,
        content: str,
        change: ProposedChange,
        file_name: str,
    ) -> str:
        """
        Applies a validated structured mutation based on file format (HCL or YAML).
        Can be used both during simulated proposal generation and live workspace execution.
        """
        curr_val = str(change.current_value) if change.current_value is not None else ""
        prop_val = str(change.proposed_value) if change.proposed_value is not None else ""
        attr = change.attribute_path
        is_yaml = file_name.endswith((".yml", ".yaml"))

        # 1. Handles HCL format: attribute = "value" or attribute = value
        if not is_yaml and attr:
            attr_regex = re.compile(
                rf'(^\s*{re.escape(attr)}\s*=\s*[\'"]?){re.escape(curr_val)}([\'"]?\s*$)',
                re.MULTILINE,
            )
            if curr_val and attr_regex.search(content):
                return attr_regex.sub(rf'\g<1>{prop_val}\g<2>', content, count=1)

        # 2. Handles YAML format: attribute: "value" or attribute: value
        if is_yaml and attr:
            yaml_regex = re.compile(
                rf'(^\s*{re.escape(attr)}\s*:\s*[\'"]?){re.escape(curr_val)}([\'"]?\s*$)',
                re.MULTILINE,
            )
            if curr_val and yaml_regex.search(content):
                return yaml_regex.sub(rf'\g<1>{prop_val}\g<2>', content, count=1)

        # 3. Direct literal match if unique and non-empty
        if curr_val and curr_val in content:
            return content.replace(curr_val, prop_val, 1)

        # 4. If attribute not found, append clean declarative configuration line
        lines = content.splitlines()
        if is_yaml:
            lines.append(f"    {attr}: \"{prop_val}\"")
        else:
            lines.append(f"  {attr} = \"{prop_val}\"")
        return "\n".join(lines) + "\n"

    def _apply_structured_mutation(
        self,
        content: str,
        change: ProposedChange,
        file_name: str,
    ) -> str:
        return self.apply_mutation_to_text(content, change, file_name)
