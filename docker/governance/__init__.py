"""
CloudPilot Safety & Autonomy Governance Subsystem.

Provides Progressive Autonomy Levels (L0-L5), 9-dimension action evaluations,
policy-as-code enforcement, emergency stop, action locks, idempotency, rate limits,
budget enforcement, automatic autonomy demotion, and cryptographic immutable audit trails.
"""

from governance.approvals import ApprovalRouter, get_approval_router
from governance.audit import ImmutableAuditTrail, get_audit_trail
from governance.autonomy import AutonomyLevelManager, DemotionController, get_autonomy_manager
from governance.control_plane import SafetyControlPlane, get_safety_control_plane
from governance.emergency import EmergencyStopManager, get_emergency_stop_manager
from governance.evaluator import MultiFactorActionEvaluator, get_action_evaluator
from governance.limits import (
    BlastRadiusGovernor,
    ExecutionBudgetTracker,
    RateLimiter,
    get_blast_radius_governor,
    get_budget_tracker,
    get_rate_limiter,
)
from governance.locks import (
    ActionLockManager,
    IdempotencyManager,
    get_action_lock_manager,
    get_idempotency_manager,
)
from governance.models import (
    ActionEvaluation,
    ActionLock,
    ActionRiskLevel,
    ApprovalDecisionRecord,
    ApprovalRequest,
    ApprovalRoute,
    ApprovalStatus,
    AuditRecord,
    AutonomyLevel,
    BusinessCriticality,
    DemotionReason,
    DemotionTrigger,
    EmergencyStopState,
    IdempotencyRecord,
    PolicyEvaluationReport,
    ProposedAction,
    ReversibilityType,
)
from governance.policy import PolicyAsCodeEngine, get_policy_engine

__all__ = [
    # Enums & Models
    "AutonomyLevel",
    "ReversibilityType",
    "ActionRiskLevel",
    "BusinessCriticality",
    "ApprovalRoute",
    "ApprovalStatus",
    "DemotionReason",
    "ProposedAction",
    "PolicyEvaluationReport",
    "ActionEvaluation",
    "ApprovalRequest",
    "ApprovalDecisionRecord",
    "EmergencyStopState",
    "ActionLock",
    "IdempotencyRecord",
    "DemotionTrigger",
    "AuditRecord",
    # Core Components & Managers
    "AutonomyLevelManager",
    "DemotionController",
    "get_autonomy_manager",
    "MultiFactorActionEvaluator",
    "get_action_evaluator",
    "PolicyAsCodeEngine",
    "get_policy_engine",
    "EmergencyStopManager",
    "get_emergency_stop_manager",
    "ActionLockManager",
    "get_action_lock_manager",
    "IdempotencyManager",
    "get_idempotency_manager",
    "RateLimiter",
    "get_rate_limiter",
    "ExecutionBudgetTracker",
    "get_budget_tracker",
    "BlastRadiusGovernor",
    "get_blast_radius_governor",
    "ApprovalRouter",
    "get_approval_router",
    "ImmutableAuditTrail",
    "get_audit_trail",
    "SafetyControlPlane",
    "get_safety_control_plane",
]
