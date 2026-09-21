"""
Cryptographic Immutable Audit Trail.

Maintains a tamper-evident, SHA-256 hash-chained log of every action,
evaluation, policy verification, approval decision, code generation, and execution result.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Tuple
import uuid

from governance.models import AuditRecord


class ImmutableAuditTrail:
    """
    Cryptographically chained audit trail.
    Each block hashes its entire content together with the previous block's hash.
    Any tampering with past records breaks the hash chain integrity verification.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, persistence_file: Optional[str] = None) -> None:
        self.persistence_file = persistence_file or str(
            Path(__file__).resolve().parent.parent / "scratch" / "state" / "governance_audit.json"
        )
        self._chain: List[AuditRecord] = []
        self._mutex = threading.Lock()
        self._load_from_disk()

    def record_action(
        self,
        actor: str,
        objective: str,
        plan: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        policy_evaluation: Optional[Dict[str, Any]] = None,
        approval: Optional[Dict[str, Any]] = None,
        code: Optional[str] = None,
        execution_result: Optional[Dict[str, Any]] = None,
        agent: str = "CloudPilot-TrueForge-Runtime",
    ) -> AuditRecord:
        """
        Append a new block to the immutable audit chain with cryptographic hash chaining.
        """
        import copy
        now = datetime.now(timezone.utc)
        with self._mutex:
            seq = len(self._chain)
            prev_hash = self._chain[-1].entry_hash if self._chain else self.GENESIS_HASH

            record = AuditRecord(
                record_id=f"aud-{uuid.uuid4().hex[:8]}",
                sequence_number=seq,
                actor=actor,
                agent=agent,
                timestamp=now,
                objective=objective,
                plan=copy.deepcopy(plan) if plan else {},
                evidence=copy.deepcopy(evidence) if evidence else {},
                policy_evaluation=copy.deepcopy(policy_evaluation) if policy_evaluation else {},
                approval=copy.deepcopy(approval) if approval else None,
                code=code,
                execution_result=copy.deepcopy(execution_result) if execution_result else {},
                previous_hash=prev_hash,
                entry_hash="",
            )
            # Compute block hash
            record.entry_hash = record.compute_hash()
            self._chain.append(record)
            self._save_to_disk_locked()
            return record

    def verify_integrity(self) -> Tuple[bool, str, Optional[int]]:
        """
        Verify the complete cryptographic integrity of the audit chain from genesis to head.
        Returns (is_valid, message, broken_index).
        """
        with self._mutex:
            if not self._chain:
                return True, "Audit trail is empty (valid)", None

            for idx, block in enumerate(self._chain):
                # 1. Verify previous hash link
                expected_prev = self._chain[idx - 1].entry_hash if idx > 0 else self.GENESIS_HASH
                if block.previous_hash != expected_prev:
                    return (
                        False,
                        f"HASH_CHAIN_BROKEN: Block #{idx} previous_hash does not match preceding block's hash",
                        idx,
                    )

                # 2. Recompute and verify current block's hash
                recomputed = block.compute_hash()
                if block.entry_hash != recomputed:
                    return (
                        False,
                        f"TAMPER_DETECTED: Block #{idx} entry_hash has been tampered with or corrupted",
                        idx,
                    )

            return True, f"Integrity verified: all {len(self._chain)} blocks in chain are cryptographically valid", None

    def get_record(self, record_id: str) -> Optional[AuditRecord]:
        with self._mutex:
            for r in self._chain:
                if r.record_id == record_id:
                    return r
            return None

    def list_records(
        self,
        limit: int = 50,
        offset: int = 0,
        actor: Optional[str] = None,
    ) -> List[AuditRecord]:
        """List audit records with pagination (newest first)."""
        with self._mutex:
            records = list(self._chain)
            if actor:
                records = [r for r in records if r.actor == actor]
            records.reverse()
            return records[offset : offset + limit]

    def count_records(self) -> int:
        with self._mutex:
            return len(self._chain)

    def clear_all(self) -> None:
        """Clear audit trail (used for isolated test runs)."""
        with self._mutex:
            self._chain.clear()
            if os.path.exists(self.persistence_file):
                try:
                    os.remove(self.persistence_file)
                except OSError:
                    pass

    # -------------------------------------------------------------------------
    # Disk Persistence
    # -------------------------------------------------------------------------
    def _save_to_disk_locked(self) -> None:
        try:
            path = Path(self.persistence_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = [r.model_dump(mode="json") for r in self._chain]
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            tmp_path.replace(path)
        except Exception:
            pass

    def _load_from_disk(self) -> None:
        try:
            path = Path(self.persistence_file)
            if path.exists():
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._chain = [AuditRecord(**item) for item in data]
        except Exception:
            self._chain = []


_audit_trail_instance: Optional[ImmutableAuditTrail] = None


def get_audit_trail() -> ImmutableAuditTrail:
    global _audit_trail_instance
    if _audit_trail_instance is None:
        _audit_trail_instance = ImmutableAuditTrail()
    return _audit_trail_instance
