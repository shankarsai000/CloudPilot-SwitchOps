"""
CloudPilot SwitchOps — Execution Orchestrator (Phase 4)

Governs the complete human-authorized, proposal-bound execution lifecycle:
OBSERVE -> ANALYZE -> OPTIMIZE -> PROPOSE -> APPROVE -> EXECUTE -> VERIFY -> RECOVER -> AUDIT

Enforces: "CloudPilot must never execute a change different from the exact change
that an authorized human approved."
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import threading
from typing import Any, Dict, List, Optional
import uuid

from app.core.errors import CloudPilotError, NotFoundError
from app.domain.approvals import (
    ApprovalPrincipal,
    ApprovalRecord,
    ApprovalStatus,
)
from app.domain.execution import (
    ExecutionRecord,
    ExecutionStatus,
    FileMutationRecord,
)
from app.domain.models import ActorType, TaskEvent, TaskEventType
from app.domain.policies import PolicyConfiguration
from app.domain.proposals import Proposal, ProposalStatus
from app.persistence.repository import TaskRepositoryInterface
from app.services.approval.approval_service import ApprovalSecurityError
from app.services.execution.change_applier import ChangeApplier, ChangeApplicationError
from app.services.execution.execution_audit import ExecutionAuditLogger
from app.services.execution.execution_policy import ExecutionPolicyEngine, PreExecutionCheckError
from app.services.execution.recovery_manager import RecoveryManager
from app.services.execution.validation_runner import ValidationRunner
from app.services.execution.workspace_manager import WorkspaceManager

logger = logging.getLogger("cloudpilot.execution.orchestrator")


class ExecutionOrchestrator:
    """
    Central controller managing isolated execution, pre-flight safety gates,
    structured mutations, post-execution verification, and automatic rollback.
    """

    def __init__(
        self,
        repository: TaskRepositoryInterface,
        workspace_manager: Optional[WorkspaceManager] = None,
        change_applier: Optional[ChangeApplier] = None,
        policy_engine: Optional[ExecutionPolicyEngine] = None,
        validation_runner: Optional[ValidationRunner] = None,
        recovery_manager: Optional[RecoveryManager] = None,
        audit_logger: Optional[ExecutionAuditLogger] = None,
    ) -> None:
        self.repository = repository
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.change_applier = change_applier or ChangeApplier()
        self.policy_engine = policy_engine or ExecutionPolicyEngine()
        self.validation_runner = validation_runner or ValidationRunner()
        self.recovery_manager = recovery_manager or RecoveryManager()
        self.audit_logger = audit_logger or ExecutionAuditLogger(repository=repository)
        self._lock = threading.RLock()
        self._active_proposals: set[str] = set()

    def execute_approved_proposal(
        self,
        proposal_id: str,
        token_string: str,
        approver: ApprovalPrincipal,
        target_workspace_root: Optional[str] = None,
        policy: Optional[PolicyConfiguration] = None,
    ) -> ExecutionRecord:
        """
        Executes an approved change proposal inside an isolated sandbox workspace.
        Enforces pre-checks, single-use token consumption, validation, and rollback.
        """
        # 1. Concurrency lock to prevent simultaneous execution of the same proposal
        with self._lock:
            if proposal_id in self._active_proposals:
                raise ApprovalSecurityError(f"Concurrent execution rejected: proposal '{proposal_id}' is already executing.")
            self._active_proposals.add(proposal_id)

        try:
            return self._execute_internal(
                proposal_id=proposal_id,
                token_string=token_string,
                approver=approver,
                target_workspace_root=target_workspace_root,
                policy=policy,
            )
        finally:
            with self._lock:
                self._active_proposals.discard(proposal_id)

    def _execute_internal(
        self,
        proposal_id: str,
        token_string: str,
        approver: ApprovalPrincipal,
        target_workspace_root: Optional[str],
        policy: Optional[PolicyConfiguration],
    ) -> ExecutionRecord:
        now = datetime.now(timezone.utc)
        execution_id = f"exec-{uuid.uuid4().hex[:10]}"

        # A. Retrieve Proposal
        proposal = self.repository.get_proposal(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal '{proposal_id}' not found", resource_type="proposal", resource_id=proposal_id)

        # B. Retrieve Approval Record
        approval = self.repository.get_approval_for_proposal(proposal_id)
        if not approval:
            raise ApprovalSecurityError(
                f"Execution blocked: Proposal '{proposal_id}' has not been approved by a human."
            )

        if approval.status != ApprovalStatus.APPROVED:
            raise ApprovalSecurityError(
                f"Execution blocked: Proposal status is '{approval.status.value}', expected APPROVED."
            )

        # Initialize Execution Record
        source_workspace = target_workspace_root or proposal.workspace_root
        execution = ExecutionRecord(
            execution_id=execution_id,
            proposal_id=proposal.proposal_id,
            proposal_hash=proposal.proposal_hash,
            approver_id=approver.principal_id,
            status=ExecutionStatus.INITIALIZING,
            workspace_path="",
            started_at=now,
            schema_version="1.0",
        )
        self.repository.save_execution(execution)

        # Audit event
        self.audit_logger.log_event(
            execution_id=execution_id,
            proposal_id=proposal_id,
            event_type="EXECUTION_INITIALIZED",
            actor_id=approver.principal_id,
            details={"approver_role": approver.role.value, "proposal_hash": proposal.proposal_hash},
        )

        # C. Pre-Execution Safety Checks
        is_safe, check_results, reasons = self.policy_engine.verify_pre_execution_safety(
            proposal=proposal,
            approval=approval,
            token_string=token_string,
            workspace_root=source_workspace,
            policy=policy,
        )

        self.audit_logger.log_event(
            execution_id=execution_id,
            proposal_id=proposal_id,
            event_type="PRE_CHECK_EVALUATED",
            actor_id="cloudpilot-policy-engine",
            details={"is_safe": is_safe, "checks": check_results, "reasons": reasons},
        )

        if not is_safe:
            execution.status = ExecutionStatus.PRE_CHECK_FAILED
            execution.error_message = "; ".join(reasons)
            execution.mark_failed(execution.error_message)
            self.repository.update_execution(execution)
            raise PreExecutionCheckError(f"Pre-execution safety checks failed: {reasons}")

        execution.status = ExecutionStatus.PRE_CHECK_PASSED
        self.repository.update_execution(execution)

        # D. Single-Use Token Consumption (Replay Protection)
        approval.mark_consumed()
        self.repository.update_approval(approval)
        self.audit_logger.log_event(
            execution_id=execution_id,
            proposal_id=proposal_id,
            event_type="TOKEN_CONSUMED",
            actor_id=approver.principal_id,
            details={"approval_id": approval.approval_id, "token_id": approval.approval_token_id},
        )

        # E. Create Isolated Workspace Sandbox
        try:
            ws_path, recorded_hashes = self.workspace_manager.create_isolated_workspace(
                execution_id=execution_id,
                source_root=source_workspace,
                allowlisted_relative_paths=proposal.source_file_paths,
            )
            execution.workspace_path = ws_path
            self.repository.update_execution(execution)
            self.audit_logger.log_event(
                execution_id=execution_id,
                proposal_id=proposal_id,
                event_type="WORKSPACE_ISOLATED",
                actor_id="workspace-manager",
                details={"workspace_path": ws_path, "files_copied": list(recorded_hashes.keys())},
            )
        except Exception as ws_err:
            execution.mark_failed(f"Workspace creation error: {ws_err}")
            self.repository.update_execution(execution)
            raise

        # F. Capture Pre-Execution Backup Snapshot
        snapshot_hashes = self.recovery_manager.create_pre_execution_snapshot(
            workspace_path=ws_path,
            relative_file_paths=proposal.source_file_paths,
        )
        self.audit_logger.log_event(
            execution_id=execution_id,
            proposal_id=proposal_id,
            event_type="SNAPSHOT_CAPTURED",
            actor_id="recovery-manager",
            details={"files_snapshotted": list(snapshot_hashes.keys())},
        )

        # G. Apply Structured Mutations
        execution.status = ExecutionStatus.EXECUTING
        self.repository.update_execution(execution)

        try:
            mutation_records = self.change_applier.apply_changes(
                workspace_path=ws_path,
                changes=proposal.canonical_proposed_changes,
            )
            execution.applied_mutations = mutation_records
            self.repository.update_execution(execution)
            self.audit_logger.log_event(
                execution_id=execution_id,
                proposal_id=proposal_id,
                event_type="MUTATIONS_APPLIED",
                actor_id="change-applier",
                details={"mutations_count": len(mutation_records)},
            )
        except Exception as mut_err:
            logger.error("Mutation failed during execution: %s; initiating rollback", mut_err)
            self._handle_rollback(
                execution=execution,
                proposal=proposal,
                ws_path=ws_path,
                reason=f"Mutation application error: {mut_err}",
            )
            raise

        # H. Post-Execution Validation
        applied_paths = [m.file_path for m in mutation_records]
        valid_passed, val_report, val_errors = self.validation_runner.validate_execution(
            workspace_path=ws_path,
            proposal=proposal,
            applied_file_paths=applied_paths,
        )
        execution.validation_results = val_report
        self.repository.update_execution(execution)

        self.audit_logger.log_event(
            execution_id=execution_id,
            proposal_id=proposal_id,
            event_type="VALIDATION_EXECUTED",
            actor_id="validation-runner",
            details={"passed": valid_passed, "errors": val_errors},
        )

        if not valid_passed:
            logger.warning("Post-execution validation failed: %s; initiating rollback", val_errors)
            self._handle_rollback(
                execution=execution,
                proposal=proposal,
                ws_path=ws_path,
                reason=f"Post-execution validation failed: {'; '.join(val_errors)}",
            )
            raise ValueError(f"Post-execution validation failed: {val_errors}")

        # I. Mark Execution and Proposal COMPLETED
        execution.mark_completed()
        self.repository.update_execution(execution)

        proposal.status = ProposalStatus.EXECUTED
        self.repository.update_proposal(proposal)

        self.audit_logger.log_event(
            execution_id=execution_id,
            proposal_id=proposal_id,
            event_type="EXECUTION_COMPLETED",
            actor_id="execution-orchestrator",
            details={
                "status": "COMPLETED",
                "mutations_applied": len(mutation_records),
                "after_hashes": val_report.get("actual_after_hashes", {}),
            },
        )

        self.repository.append_event(
            TaskEvent(
                task_id=proposal.task_id,
                correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
                event_type=TaskEventType.TASK_UPDATED,
                actor_id="cloudpilot-execution-engine",
                actor_type=ActorType.AGENT,
                payload={
                    "event": "EXECUTION_COMPLETED",
                    "execution_id": execution.execution_id,
                    "proposal_id": proposal.proposal_id,
                    "status": "COMPLETED",
                    "applied_mutations": len(mutation_records),
                },
            )
        )

        logger.info("Execution '%s' for proposal '%s' completed successfully.", execution_id, proposal_id)
        return execution

    def _handle_rollback(
        self,
        execution: ExecutionRecord,
        proposal: Proposal,
        ws_path: str,
        reason: str,
    ) -> None:
        """
        Executes automatic file recovery when mutation or validation fails.
        """
        execution.status = ExecutionStatus.ROLLING_BACK
        self.repository.update_execution(execution)
        self.audit_logger.log_event(
            execution_id=execution.execution_id,
            proposal_id=proposal.proposal_id,
            event_type="RECOVERY_INITIATED",
            actor_id="recovery-manager",
            details={"reason": reason},
        )

        restored_ok, restored_files, rec_err = self.recovery_manager.rollback_workspace(
            workspace_path=ws_path,
            expected_before_hashes=proposal.before_state_file_hashes,
        )

        if restored_ok:
            execution.mark_rolled_back(f"Rolled back {len(restored_files)} files. Reason: {reason}")
            self.audit_logger.log_event(
                execution_id=execution.execution_id,
                proposal_id=proposal.proposal_id,
                event_type="RECOVERY_COMPLETED",
                actor_id="recovery-manager",
                details={"restored_files": restored_files, "status": "ROLLED_BACK"},
            )
        else:
            execution.status = ExecutionStatus.RECOVERY_FAILED
            execution.error_message = f"Rollback failed: {rec_err}. Original trigger: {reason}"
            self.audit_logger.log_event(
                execution_id=execution.execution_id,
                proposal_id=proposal.proposal_id,
                event_type="RECOVERY_FAILED",
                actor_id="recovery-manager",
                details={"error": rec_err, "status": "RECOVERY_FAILED"},
            )

        self.repository.update_execution(execution)

    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        return self.repository.get_execution(execution_id)

    def get_execution_for_proposal(self, proposal_id: str) -> Optional[ExecutionRecord]:
        return self.repository.get_execution_for_proposal(proposal_id)

    def execute_proposal(
        self,
        proposal_id: str,
        approval_token: str,
        principal: ApprovalPrincipal,
        target_workspace: Optional[str] = None,
        policy: Optional[PolicyConfiguration] = None,
    ) -> ExecutionRecord:
        """Convenience alias for execute_approved_proposal."""
        return self.execute_approved_proposal(
            proposal_id=proposal_id,
            token_string=approval_token,
            approver=principal,
            target_workspace_root=target_workspace,
            policy=policy,
        )
