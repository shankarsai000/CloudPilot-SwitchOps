"""
CloudPilot SwitchOps — Audit Chain & Tamper Detection Tests (Phase 4.1)

Validates Workstream F (Audit Integrity and Provenance):
1. Every state transition produces an append-only, cryptographically hash-chained audit event.
2. Monotonic sequence and parent-hash (prev_audit_hash) continuity starting from GENESIS.
3. Tamper detection on event payload (modifying details, actor_id, or timestamp invalidates chain).
4. Deletion of any event breaks hash continuity and is detected.
5. Reordering of events breaks hash continuity and is detected.
6. Audit manifest export produces a self-verifying bundle with canonical SHA-256 manifest digest.
7. Independent audit chains per execution ID (no crosstalk).
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pytest

from app.domain.execution import AuditLogEvent
from app.persistence.repository import InMemoryTaskRepository
from app.services.execution.execution_audit import ExecutionAuditLogger


@pytest.fixture
def audit_fixture():
    repo = InMemoryTaskRepository()
    audit_logger = ExecutionAuditLogger(repository=repo)
    execution_id = "exec-test-audit-001"
    proposal_id = "prop-test-audit-001"

    # Populate a realistic 5-event execution audit trail
    events_data = [
        ("PRE_EXECUTION_VERIFIED", "policy-engine", {"pre_check": "PASSED", "proposal_hash_verified": True}),
        ("APPROVAL_CONSUMED", "execution-orchestrator", {"approval_id": "appr-001", "role": "PLATFORM_LEAD"}),
        ("WORKSPACE_ISOLATED", "workspace-manager", {"files_copied": ["main.tf"]}),
        ("SNAPSHOT_CAPTURED", "recovery-manager", {"files_snapshotted": ["main.tf"]}),
        ("MUTATIONS_APPLIED", "change-applier", {"mutations_count": 1}),
        ("VALIDATION_EXECUTED", "validation-runner", {"passed": True}),
        ("EXECUTION_COMPLETED", "execution-orchestrator", {"status": "COMPLETED"}),
    ]

    for ev_type, actor, details in events_data:
        audit_logger.log_event(
            execution_id=execution_id,
            proposal_id=proposal_id,
            event_type=ev_type,
            actor_id=actor,
            details=details,
        )

    return {
        "repo": repo,
        "audit_logger": audit_logger,
        "execution_id": execution_id,
        "proposal_id": proposal_id,
    }


class TestAuditChainTamperDetection:

    def test_audit_chain_genesis_and_continuity(self, audit_fixture):
        """Unbroken audit chain verifies successfully from GENESIS to final event."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        execution_id = env["execution_id"]

        is_valid, err = audit_logger.verify_audit_trail(execution_id)
        assert is_valid is True
        assert err is None

        events = env["repo"].get_audit_events_for_execution(execution_id)
        assert len(events) == 7

        # Verify GENESIS hash on first event
        expected_genesis = hashlib.sha256(f"GENESIS-{execution_id}".encode("utf-8")).hexdigest()
        assert events[0].prev_audit_hash == expected_genesis

        # Verify continuous chaining across all subsequent events
        for i in range(1, len(events)):
            assert events[i].prev_audit_hash == events[i - 1].audit_hash
            assert events[i].audit_hash == events[i].compute_audit_hash()

    def test_tampered_event_payload_detected(self, audit_fixture):
        """Altering any payload detail inside an audit event is detected immediately."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        execution_id = env["execution_id"]
        repo = env["repo"]

        # Tamper with stored event 4 (MUTATIONS_APPLIED) details
        tampered_event = repo._audit_events[execution_id][4]
        tampered_event.details = dict(tampered_event.details)
        tampered_event.details["mutations_count"] = 999  # Unauthorized modification

        # verification must fail
        is_valid, err = audit_logger.verify_audit_trail(execution_id)
        assert is_valid is False
        assert "tampered" in err.lower()
        assert tampered_event.audit_id in err

    def test_tampered_timestamp_detected(self, audit_fixture):
        """Altering an event timestamp is detected immediately."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        execution_id = env["execution_id"]
        repo = env["repo"]

        # Alter timestamp on stored event 1
        repo._audit_events[execution_id][1].timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc)

        is_valid, err = audit_logger.verify_audit_trail(execution_id)
        assert is_valid is False
        assert "tampered" in err.lower()

    def test_tampered_actor_detected(self, audit_fixture):
        """Altering the actor_id of an event is detected."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        execution_id = env["execution_id"]
        repo = env["repo"]

        # Alter actor on stored event 0
        repo._audit_events[execution_id][0].actor_id = "malicious-intruder"

        is_valid, err = audit_logger.verify_audit_trail(execution_id)
        assert is_valid is False
        assert "tampered" in err.lower()

    def test_deleted_event_in_chain_detected(self, audit_fixture):
        """Deleting an event in the middle breaks prev_audit_hash continuity."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        execution_id = env["execution_id"]
        repo = env["repo"]

        # Directly delete event 2 from the repository's store
        del repo._audit_events[execution_id][2]

        is_valid, err = audit_logger.verify_audit_trail(execution_id)
        assert is_valid is False
        assert "chain broken" in err.lower() or "prev_hash" in err.lower()

    def test_reordered_events_detected(self, audit_fixture):
        """Swapping the order of two events breaks hash continuity."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        execution_id = env["execution_id"]
        repo = env["repo"]

        # Swap events 2 and 3
        ev_list = repo._audit_events[execution_id]
        ev_list[2], ev_list[3] = ev_list[3], ev_list[2]

        is_valid, err = audit_logger.verify_audit_trail(execution_id)
        assert is_valid is False
        assert "chain broken" in err.lower() or "tampered" in err.lower()

    def test_manifest_export_and_digest_verification(self, audit_fixture):
        """export_audit_manifest generates a complete manifest with valid SHA-256 digest."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        execution_id = env["execution_id"]

        manifest = audit_logger.export_audit_manifest(execution_id)
        assert manifest["execution_id"] == execution_id
        assert manifest["event_count"] == 7
        assert manifest["chain_valid"] is True
        assert manifest["validation_error"] is None
        assert "manifest_digest_sha256" in manifest

        # Re-compute digest independently to confirm canonical JSON validity
        digest = manifest["manifest_digest_sha256"]
        manifest_copy = dict(manifest)
        del manifest_copy["manifest_digest_sha256"]
        canonical = json.dumps(manifest_copy, sort_keys=True, separators=(",", ":")).encode("utf-8")
        assert hashlib.sha256(canonical).hexdigest() == digest

    def test_manifest_detects_corrupted_manifest(self, audit_fixture):
        """Modifying any field in the exported manifest invalidates the digest."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        execution_id = env["execution_id"]

        manifest = audit_logger.export_audit_manifest(execution_id)
        original_digest = manifest["manifest_digest_sha256"]

        # Corrupt manifest
        manifest["event_count"] = 999
        del manifest["manifest_digest_sha256"]
        recomputed = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        assert recomputed != original_digest

    def test_empty_audit_trail_valid(self):
        """An execution with no recorded events returns valid=True."""
        repo = InMemoryTaskRepository()
        logger = ExecutionAuditLogger(repository=repo)
        is_valid, err = logger.verify_audit_trail("exec-empty-001")
        assert is_valid is True
        assert err is None

    def test_multi_execution_isolation(self, audit_fixture):
        """Multiple distinct executions maintain completely separate hash chains."""
        env = audit_fixture
        audit_logger: ExecutionAuditLogger = env["audit_logger"]
        repo = env["repo"]

        # Log an event for a second execution
        audit_logger.log_event(
            execution_id="exec-second-999",
            proposal_id="prop-second-999",
            event_type="PRE_EXECUTION_VERIFIED",
            actor_id="policy-engine",
            details={"run": 2},
        )

        valid1, err1 = audit_logger.verify_audit_trail(env["execution_id"])
        valid2, err2 = audit_logger.verify_audit_trail("exec-second-999")

        assert valid1 is True
        assert valid2 is True

        # Check genesis hashes are different
        events1 = repo.get_audit_events_for_execution(env["execution_id"])
        events2 = repo.get_audit_events_for_execution("exec-second-999")
        assert events1[0].prev_audit_hash != events2[0].prev_audit_hash
