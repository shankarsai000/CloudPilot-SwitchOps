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

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ActorType",
    "ApplicabilityStatus",
    "AssessmentSummary",
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
    "Finding",
    "FindingCategory",
    "FindingSeverity",
    "ImpactLevel",
    "InfrastructureInventory",
    "InteractionType",
    "ObjectiveDimension",
    "ObjectiveScores",
    "OperationalComplexity",
    "PREFERENCE_WEIGHTS",
    "ParetoStatus",
    "PolicyConfiguration",
    "PreferenceProfile",
    "ProposedChange",
    "ResourceCategory",
    "Task",
    "TaskEvent",
    "TaskEventType",
    "TaskStatus",
]
