"""
CloudPilot Outcome Verification, Deterministic Rollback, Savings Attribution, & Learning Loop.
"""

from verification.attribution import (
    PortfolioSavingsSummary,
    SavingsAttributionEngine,
    get_savings_attribution_engine,
)
from verification.engine import OutcomeVerificationEngine, get_verification_engine
from verification.incident import PostExecutionIncidentDetector, get_incident_detector
from verification.learning_loop import LearningLoopBridge, get_learning_loop_bridge
from verification.models import (
    ActualOutcome,
    ExpectedOutcome,
    IncidentSeverity,
    LearningUpdateReport,
    OutcomeDimension,
    OutcomeReport,
    OutcomeVerdict,
    PostExecutionIncident,
    RollbackPlan,
    RollbackResult,
    SafetyThresholds,
    SavingsAttribution,
)
from verification.rollback import AutomatedRollbackManager, get_rollback_manager
from verification.routes import router as verification_router

__all__ = [
    # Models
    "OutcomeVerdict",
    "IncidentSeverity",
    "OutcomeDimension",
    "SafetyThresholds",
    "ExpectedOutcome",
    "ActualOutcome",
    "OutcomeReport",
    "RollbackPlan",
    "RollbackResult",
    "SavingsAttribution",
    "PostExecutionIncident",
    "LearningUpdateReport",
    # Engines & Managers
    "OutcomeVerificationEngine",
    "get_verification_engine",
    "AutomatedRollbackManager",
    "get_rollback_manager",
    "SavingsAttributionEngine",
    "PortfolioSavingsSummary",
    "get_savings_attribution_engine",
    "PostExecutionIncidentDetector",
    "get_incident_detector",
    "LearningLoopBridge",
    "get_learning_loop_bridge",
    # Router
    "verification_router",
]
