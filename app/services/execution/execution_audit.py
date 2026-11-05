"""
CloudPilot SwitchOps — Execution Audit Logger (Phase 4)

Manages append-only execution audit trails with SHA-256 cryptographic hash-chaining
across all pre-checks, workspace isolations, mutations, validations, and rollbacks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.domain.execution import AuditLogEvent
from app.persistence.repository import TaskRepositoryInterface

logger = logging.getLogger("cloudpilot.execution.audit")


class ExecutionAuditLogger:
    """
    Appends verifiable, cryptographically chained audit events for every execution run.
    """

    def __init__(self, repository: TaskRepositoryInterface) -> None:
        self.repository = repository
        self._last_hashes: Dict[str, str] = {}

    def log_event(
        self,
        execution_id: str,
        proposal_id: str,
        event_type: str,
        actor_id: str,
        details: Dict[str, Any],
    ) -> AuditLogEvent:
        """
        Creates, hash-chains, and persists an append-only execution audit event.
        """
        # Determine previous hash in chain
        if execution_id in self._last_hashes:
            prev_hash = self._last_hashes[execution_id]
        else:
            # Query existing events from repository to resume chain
            existing = self.repository.get_audit_events_for_execution(execution_id)
            if existing:
                prev_hash = existing[-1].audit_hash
            else:
                prev_hash = hashlib.sha256(f"GENESIS-{execution_id}".encode("utf-8")).hexdigest()

        now = datetime.now(timezone.utc)
        audit_id = f"audit-{uuid.uuid4().hex[:12]}"
        event = AuditLogEvent(
            audit_id=audit_id,
            execution_id=execution_id,
            proposal_id=proposal_id,
            event_type=event_type,
            actor_id=actor_id,
            timestamp=now,
            details=details,
            prev_audit_hash=prev_hash,
        )
        event.audit_hash = event.compute_audit_hash()
        self._last_hashes[execution_id] = event.audit_hash

        saved = self.repository.save_audit_event(event)
        logger.debug(
            "Audit event [%s] recorded for execution '%s' (hash=%s)",
            event_type,
            execution_id,
            event.audit_hash[:16],
        )
        return saved

    def verify_audit_trail(self, execution_id: str) -> Tuple[bool, Optional[str]]:
        """
        Verifies the cryptographic integrity of the audit hash chain for an execution.
        Returns: (is_valid, error_reason)
        """
        events = self.repository.get_audit_events_for_execution(execution_id)
        if not events:
            return True, None

        expected_prev = hashlib.sha256(f"GENESIS-{execution_id}".encode("utf-8")).hexdigest()

        for idx, evt in enumerate(events):
            if evt.prev_audit_hash != expected_prev:
                return False, (
                    f"Audit chain broken at event {idx} ({evt.audit_id}): "
                    f"expected prev_hash {expected_prev[:16]}, got {evt.prev_audit_hash[:16]}"
                )

            computed_hash = evt.compute_audit_hash()
            if evt.audit_hash != computed_hash:
                return False, (
                    f"Audit event {idx} ({evt.audit_id}) tampered: "
                    f"recorded hash {evt.audit_hash[:16]}, computed {computed_hash[:16]}"
                )

            expected_prev = evt.audit_hash

        return True, None
