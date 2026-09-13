"""
CloudPilot Safety & Autonomy Control Plane — Domain Models.

Defines schemas for:
- Progressive Autonomy Levels (L0 to L5)
- 9-Factor Action Evaluation (risk, confidence, criticality, policy, blast radius, reversibility, simulation, history, approval)
- Policy-as-Code Rules & Compliance Reports
- Multi-Tier Approval Workflows
- Emergency Stop (Kill Switch) Scopes
- Action Locks & Idempotency
- Autonomy Demotion Triggers
- Cryptographic SHA-256 Hash-Chained Audit Trail
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════

class AutonomyLevel(str, Enum):
    """
    Progressive Autonomy Levels for CloudPilot operations.
    """
    L0_OBSERVE = "L0_OBSERVE"          # Observe only: telemetry and inventory monitoring
    L1_RECOMMEND = "L1_RECOMMEND"      # Propose optimizations; zero simulation or execution
    L2_SIMULATE = "L2_SIMULATE"        # Digital twin simulations & dry-runs; zero live execution
    L3_APPROVAL = "L3_APPROVAL"        # Human-in-the-loop: plan generated, execution strictly requires approval
    L4_LIMITED = "L4_LIMITED"          # Autonomous execution for safe, low-risk, reversible dev/test actions
    L5_FULL = "L5_FULL"                # Full autonomous execution across allowed scopes within policy boundaries


class ReversibilityType(str, Enum):
    """Whether an infrastructure modification can be rolled back."""
    REVERSIBLE = "REVERSIBLE"          # e.g., instance resizing, adjusting autoscaling, modifying tags
    IRREVERSIBLE = "IRREVERSIBLE"      # e.g., bucket wipe, disk deletion, database drop, cluster termination


class ActionRiskLevel(str, Enum):
    """Qualitative action risk category."""
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BusinessCriticality(str, Enum):
    """Application/service criticality tier."""
    TIER_1_MISSION_CRITICAL = "TIER_1_MISSION_CRITICAL"
    TIER_2_IMPORTANT = "TIER_2_IMPORTANT"
    TIER_3_INTERNAL = "TIER_3_INTERNAL"
    DEV_TEST = "DEV_TEST"


class ApprovalRoute(str, Enum):
    """Routing destination for human-in-the-loop approval."""
    AUTO_EXECUTE = "AUTO_EXECUTE"
    ENGINEERING_LEAD = "ENGINEERING_LEAD"
    SRE_TEAM = "SRE_TEAM"
    SECURITY_TEAM = "SECURITY_TEAM"
    EXECUTIVE_APPROVAL = "EXECUTIVE_APPROVAL"
    BLOCKED = "BLOCKED"


class ApprovalStatus(str, Enum):
    """Status of an approval request."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONFLICTED = "CONFLICTED"
    CANCELLED = "CANCELLED"


class DemotionReason(str, Enum):
    """Triggers that cause automatic demotion of autonomy level."""
    CONFIDENCE_DECREASED = "CONFIDENCE_DECREASED"
    REPEATED_FAILURES = "REPEATED_FAILURES"
    ROLLBACK_SPIKE = "ROLLBACK_SPIKE"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    UNEXPECTED_BEHAVIOR = "UNEXPECTED_BEHAVIOR"
    EMERGENCY_STOP_TRIGGERED = "EMERGENCY_STOP_TRIGGERED"
    MANUAL_OPERATOR_DEMOTION = "MANUAL_OPERATOR_DEMOTION"


# ═══════════════════════════════════════════════════════════════
# Action & Evaluation Models
# ═══════════════════════════════════════════════════════════════

class ProposedAction(BaseModel):
    """Discrete proposed infrastructure operation."""
    action_id: str = Field(default_factory=lambda: f"act-{uuid.uuid4().hex[:8]}")
    action_type: str = Field(..., description="e.g. rightsize_instance, terminate_idle, archive_volume, modify_sg")
    target_resource_id: str = Field(..., description="Target cloud resource ID")
    target_service: str = Field("unknown", description="Associated application or service name")
    environment: str = Field("dev", description="Environment: dev, staging, prod")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action specific parameters")
    estimated_cost_impact_usd: float = Field(0.0, description="Monthly dollar change (+ increase, - savings)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyEvaluationReport(BaseModel):
    """Summary of policy-as-code evaluation against a proposed action."""
    is_compliant: bool
    policy_checks_passed: List[str] = Field(default_factory=list)
    policy_violations: List[str] = Field(default_factory=list)
    active_change_freeze: bool = False
    in_maintenance_window: bool = True
    in_business_hours: bool = False
    compliance_frameworks_satisfied: bool = True
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActionEvaluation(BaseModel):
    """
    Comprehensive evaluation of an action across all 9 required dimensions:
    1. Risk
    2. Confidence
    3. Business Criticality
    4. Policy
    5. Blast Radius
    6. Reversibility
    7. Simulation Result
    8. Historical Success
    9. Required Approval
    """
    action_id: str
    target_resource_id: str
    action_type: str
    environment: str

    # Dimension 1: Risk
    risk_level: ActionRiskLevel = ActionRiskLevel.LOW
    risk_score: float = Field(0.1, description="Quantitative risk score 0.0 to 1.0")

    # Dimension 2: Confidence
    confidence_score: float = Field(85.0, description="Confidence score 0 to 100")
    confidence_breakdown: Dict[str, float] = Field(default_factory=dict)

    # Dimension 3: Business Criticality
    business_criticality: BusinessCriticality = BusinessCriticality.DEV_TEST

    # Dimension 4: Policy
    policy_report: PolicyEvaluationReport

    # Dimension 5: Blast Radius
    blast_radius_level: ActionRiskLevel = ActionRiskLevel.LOW
    dependent_services_count: int = 0
    blast_radius_score: float = Field(0.05, description="Quantitative blast radius 0.0 to 1.0")

    # Dimension 6: Reversibility
    reversibility: ReversibilityType = ReversibilityType.REVERSIBLE

    # Dimension 7: Simulation Result
    simulation_verified: bool = True
    predicted_slo_impact_pct: float = 0.0
    predicted_headroom_healthy: bool = True

    # Dimension 8: Historical Success
    historical_success_rate: float = Field(1.0, description="Historical success rate 0.0 to 1.0")
    historical_executions_count: int = 10

    # Dimension 9: Required Approval
    required_approval: ApprovalRoute = ApprovalRoute.AUTO_EXECUTE

    # Overall Authorization Verdict
    can_auto_execute: bool = False
    requires_approval: bool = True
    is_blocked: bool = False
    verdict_reason: str = ""
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# Approval & Workflow Models
# ═══════════════════════════════════════════════════════════════

class ApprovalDecisionRecord(BaseModel):
    """A human approver's verdict on a pending request."""
    decision_id: str = Field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:8]}")
    approver: str = Field(..., description="Identity of the approver (e.g., alice@enterprise.com)")
    role: str = Field("engineer", description="Role: lead, sre, security, executive")
    status: ApprovalStatus = ApprovalStatus.APPROVED
    reason: Optional[str] = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalRequest(BaseModel):
    """Tracked approval request for an action or plan."""
    request_id: str = Field(default_factory=lambda: f"apr-{uuid.uuid4().hex[:8]}")
    action: ProposedAction
    evaluation: ActionEvaluation
    required_route: ApprovalRoute
    status: ApprovalStatus = ApprovalStatus.PENDING
    decisions: List[ApprovalDecisionRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="Timestamp after which this request expires")
    finalized_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════════
# Safety Control & Lock Models
# ═══════════════════════════════════════════════════════════════

class EmergencyStopState(BaseModel):
    """Current state of the emergency stop mechanism."""
    is_active: bool = False
    scope: str = Field("global", description="'global' or specific environment/service e.g. 'prod'")
    reason: Optional[str] = None
    activated_by: Optional[str] = None
    activated_at: Optional[datetime] = None


class ActionLock(BaseModel):
    """Exclusive lock on a target cloud resource."""
    lock_id: str = Field(default_factory=lambda: f"lck-{uuid.uuid4().hex[:8]}")
    resource_id: str
    action_type: str
    held_by: str = Field(..., description="Agent or operation ID holding the lock")
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="Expiration timestamp (TTL)")


class IdempotencyRecord(BaseModel):
    """Cached execution outcome for an idempotency key."""
    idempotency_key: str
    action_id: str
    status: str
    result_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime


class DemotionTrigger(BaseModel):
    """Record of an automatic autonomy demotion event."""
    trigger_id: str = Field(default_factory=lambda: f"dem-{uuid.uuid4().hex[:8]}")
    reason: DemotionReason
    previous_level: AutonomyLevel
    new_level: AutonomyLevel
    details: str
    metrics_snapshot: Dict[str, Any] = Field(default_factory=dict)
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# Cryptographic Immutable Audit Trail Models
# ═══════════════════════════════════════════════════════════════

class AuditRecord(BaseModel):
    """
    Cryptographically hash-chained immutable audit entry for every action.
    Every record contains SHA-256(previous_hash + payload) -> entry_hash.
    """
    record_id: str = Field(default_factory=lambda: f"aud-{uuid.uuid4().hex[:8]}")
    sequence_number: int
    actor: str = Field(..., description="Initiator: agent ID, user, or system")
    agent: str = Field("CloudPilot-TrueForge-Runtime", description="Agent name and version")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    objective: str = Field(..., description="Natural-language or operational objective")
    plan: Dict[str, Any] = Field(default_factory=dict, description="Structured execution plan")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Discovery and telemetry evidence")
    policy_evaluation: Dict[str, Any] = Field(default_factory=dict, description="Policy-as-code report")
    approval: Optional[Dict[str, Any]] = None
    code: Optional[str] = Field(None, description="Generated Terraform HCL or script")
    execution_result: Dict[str, Any] = Field(default_factory=dict, description="Execution / sandbox outcome")
    previous_hash: str = Field(..., description="SHA-256 of preceding audit record")
    entry_hash: str = Field("", description="SHA-256 of this record including previous_hash")

    def compute_hash(self) -> str:
        """Compute SHA-256 digest of this audit block."""
        payload = {
            "record_id": self.record_id,
            "sequence_number": self.sequence_number,
            "actor": self.actor,
            "agent": self.agent,
            "timestamp": self.timestamp.isoformat(),
            "objective": self.objective,
            "plan": self.plan,
            "evidence": self.evidence,
            "policy_evaluation": self.policy_evaluation,
            "approval": self.approval,
            "code": self.code,
            "execution_result": self.execution_result,
            "previous_hash": self.previous_hash,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
