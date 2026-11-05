"""CloudPilot SwitchOps domain package."""

from app.domain.candidates import (
    ApplicabilityStatus,
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
    ProposedChange,
)
from app.domain.constraints import (
    ConstraintResult,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintType,
)
from app.domain.decisions import (
    CandidateEvaluation,
    CandidateInteraction,
    DecisionReport,
    DecisionRun,
    InteractionType,
    ParetoStatus,
)
from app.domain.finding import (
    AssessmentSummary,
    Finding,
    FindingCategory,
    FindingSeverity,
)
from app.domain.inventory import (
    DiscoveredResource,
    InfrastructureInventory,
    ResourceCategory,
)
from app.domain.models import (
    ActorType,
    ALLOWED_TRANSITIONS,
    Evidence,
    EvidenceSeverity,
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)
from app.domain.objectives import (
    ObjectiveDimension,
    ObjectiveScores,
    PREFERENCE_WEIGHTS,
    PreferenceProfile,
)
from app.domain.policies import PolicyConfiguration
from app.domain.proposals import Proposal, ProposalStatus
from app.domain.approvals import (
    ApprovalPrincipal,
    ApprovalRecord,
    ApprovalStatus,
    ApprovalTokenPayload,
    ApproverRole,
    PERMITTED_APPROVAL_ROLES,
)
from app.domain.execution import (
    AuditLogEvent,
    ExecutionRecord,
    ExecutionStatus,
    FileMutationRecord,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ActorType",
    "ApplicabilityStatus",
    "ApprovalPrincipal",
    "ApprovalRecord",
    "ApprovalStatus",
    "ApprovalTokenPayload",
    "ApproverRole",
    "AssessmentSummary",
    "AuditLogEvent",
    "Candidate",
    "CandidateEvaluation",
    "CandidateInteraction",
    "CandidateType",
    "ConstraintResult",
    "ConstraintSeverity",
    "ConstraintStatus",
    "ConstraintType",
    "DecisionReport",
    "DecisionRun",
    "DiscoveredResource",
    "Evidence",
    "EvidenceSeverity",
    "ExecutionRecord",
    "ExecutionStatus",
    "FileMutationRecord",
    "Finding",
    "FindingCategory",
    "FindingSeverity",
    "ImpactLevel",
    "InfrastructureInventory",
    "InteractionType",
    "ObjectiveDimension",
    "ObjectiveScores",
    "OperationalComplexity",
    "PERMITTED_APPROVAL_ROLES",
    "PREFERENCE_WEIGHTS",
    "ParetoStatus",
    "PolicyConfiguration",
    "PreferenceProfile",
    "Proposal",
    "ProposalStatus",
    "ProposedChange",
    "ResourceCategory",
    "Task",
    "TaskEvent",
    "TaskEventType",
    "TaskStatus",
]
