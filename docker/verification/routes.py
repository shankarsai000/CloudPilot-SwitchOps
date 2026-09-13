"""
FastAPI Router for Outcome Verification, Automated Rollback, Savings Attribution, & Learning Loop.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from verification.attribution import get_savings_attribution_engine, PortfolioSavingsSummary
from verification.engine import get_verification_engine
from verification.incident import get_incident_detector
from verification.learning_loop import get_learning_loop_bridge
from verification.models import (
    ActualOutcome,
    ExpectedOutcome,
    LearningUpdateReport,
    OutcomeReport,
    PostExecutionIncident,
    RollbackPlan,
    RollbackResult,
    SavingsAttribution,
    SafetyThresholds,
)
from verification.rollback import get_rollback_manager

router = APIRouter(prefix="/verification", tags=["verification"])


# --- Request Schemas ---

class CreateExpectedOutcomeRequest(BaseModel):
    action_id: str
    target_resource_id: str
    baseline_monthly_cost_usd: float
    expected_monthly_savings_usd: float
    target_service: str = "unknown"
    expected_cpu_utilization_pct: float = 45.0
    expected_memory_headroom_pct: float = 40.0
    expected_latency_p99_ms: float = 45.0
    expected_availability_pct: float = 99.99
    expected_risk_level: str = "LOW"
    thresholds: Optional[SafetyThresholds] = None


class VerifyOutcomeRequest(BaseModel):
    action_id: str
    target_resource_id: str
    measured_monthly_cost_usd: float
    measured_savings_usd: float
    measured_cpu_utilization_pct: float
    measured_memory_headroom_pct: float
    measured_latency_p99_ms: float
    measured_availability_pct: float = 99.99
    measured_error_rate_pct: float = 0.01
    measured_risk_level: str = "LOW"
    observed_incidents_count: int = 0
    auto_trigger_rollback_on_breach: bool = True
    feed_to_learning_loop: bool = True


class ExecuteRollbackRequest(BaseModel):
    action_id: str
    target_resource_id: str
    original_action_type: str = "rightsize_instance"
    original_parameters: Dict[str, Any] = Field(default_factory=dict)
    baseline_snapshot: Dict[str, Any] = Field(default_factory=dict)
    actor: str = "CloudPilot-Operator"
    reason: str = "Manual rollback request"


class AttributeSavingsRequest(BaseModel):
    action_id: str
    target_resource_id: str
    predicted_monthly_savings_usd: float
    verified_monthly_savings_usd: float
    target_service: str = "unknown"
    confidence_calibration_factor: float = 0.95
    variance_discount_pct: float = 0.05


class IngestFeedbackRequest(BaseModel):
    action_id: str
    target_resource_id: str
    action: str
    feedback_type: str = Field(..., description="'OVERRIDE' or 'REJECTION'")
    actor: str
    reason: str = ""


# --- Endpoints ---

@router.post("/expected", response_model=ExpectedOutcome)
def create_expected_outcome(req: CreateExpectedOutcomeRequest) -> ExpectedOutcome:
    """Generate and store ex-ante expectations across 5 dimensions."""
    engine = get_verification_engine()
    return engine.generate_expected_outcome(
        action_id=req.action_id,
        target_resource_id=req.target_resource_id,
        baseline_monthly_cost_usd=req.baseline_monthly_cost_usd,
        expected_monthly_savings_usd=req.expected_monthly_savings_usd,
        target_service=req.target_service,
        expected_cpu_utilization_pct=req.expected_cpu_utilization_pct,
        expected_memory_headroom_pct=req.expected_memory_headroom_pct,
        expected_latency_p99_ms=req.expected_latency_p99_ms,
        expected_availability_pct=req.expected_availability_pct,
        expected_risk_level=req.expected_risk_level,
        thresholds=req.thresholds,
    )


@router.post("/verify", response_model=OutcomeReport)
def verify_outcome(req: VerifyOutcomeRequest) -> OutcomeReport:
    """Compare expected vs actual outcome, evaluate thresholds, and trigger rollback/learning if needed."""
    engine = get_verification_engine()
    expected = engine.get_expected(req.action_id)
    if not expected:
        # Synthesize fallback expected outcome if not pre-registered
        expected = engine.generate_expected_outcome(
            action_id=req.action_id,
            target_resource_id=req.target_resource_id,
            baseline_monthly_cost_usd=req.measured_monthly_cost_usd + req.measured_savings_usd,
            expected_monthly_savings_usd=req.measured_savings_usd,
        )

    actual = engine.collect_actual_outcome(
        action_id=req.action_id,
        target_resource_id=req.target_resource_id,
        measured_monthly_cost_usd=req.measured_monthly_cost_usd,
        measured_savings_usd=req.measured_savings_usd,
        measured_cpu_utilization_pct=req.measured_cpu_utilization_pct,
        measured_memory_headroom_pct=req.measured_memory_headroom_pct,
        measured_latency_p99_ms=req.measured_latency_p99_ms,
        measured_availability_pct=req.measured_availability_pct,
        measured_error_rate_pct=req.measured_error_rate_pct,
        measured_risk_level=req.measured_risk_level,
        observed_incidents_count=req.observed_incidents_count,
    )

    report = engine.verify_and_generate_report(expected, actual)

    # Automated Rollback on threshold breach
    if report.rollback_required and req.auto_trigger_rollback_on_breach:
        rollback_mgr = get_rollback_manager()
        plan = rollback_mgr.generate_rollback_plan(
            action_id=report.action_id,
            target_resource_id=report.target_resource_id,
            original_action_type="rightsize_instance",
        )
        rollback_mgr.execute_rollback(plan=plan, reason="Automated rollback due to safety threshold breach")

    # Feed into M8 learning loop
    if req.feed_to_learning_loop:
        bridge = get_learning_loop_bridge()
        bridge.ingest_outcome(report)

    # Register 3-way savings attribution
    attr_engine = get_savings_attribution_engine()
    attr_engine.attribute_savings(
        action_id=report.action_id,
        target_resource_id=report.target_resource_id,
        predicted_monthly_savings_usd=expected.expected_monthly_savings_usd,
        verified_monthly_savings_usd=actual.measured_savings_usd,
        target_service=expected.target_service,
    )

    return report


@router.get("/reports", response_model=List[OutcomeReport])
def list_outcome_reports() -> List[OutcomeReport]:
    """List all generated outcome reports."""
    return get_verification_engine().list_reports()


@router.get("/reports/{action_id}", response_model=OutcomeReport)
def get_outcome_report(action_id: str) -> OutcomeReport:
    """Retrieve outcome report by action ID."""
    report = get_verification_engine().get_report(action_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"No outcome report found for action {action_id}")
    return report


@router.post("/rollback", response_model=RollbackResult)
def execute_rollback(req: ExecuteRollbackRequest) -> RollbackResult:
    """Execute deterministic, idempotent, and auditable rollback."""
    rollback_mgr = get_rollback_manager()
    plan = rollback_mgr.generate_rollback_plan(
        action_id=req.action_id,
        target_resource_id=req.target_resource_id,
        original_action_type=req.original_action_type,
        original_parameters=req.original_parameters,
        baseline_snapshot=req.baseline_snapshot,
    )
    return rollback_mgr.execute_rollback(plan=plan, actor=req.actor, reason=req.reason)


@router.get("/rollback/history", response_model=List[RollbackResult])
def list_rollback_history() -> List[RollbackResult]:
    """List all executed rollbacks."""
    return get_rollback_manager().list_executed_rollbacks()


@router.post("/attribution", response_model=SavingsAttribution)
def register_savings_attribution(req: AttributeSavingsRequest) -> SavingsAttribution:
    """Compute and record 3-way savings attribution (Predicted, Verified, Annualized)."""
    engine = get_savings_attribution_engine()
    return engine.attribute_savings(
        action_id=req.action_id,
        target_resource_id=req.target_resource_id,
        predicted_monthly_savings_usd=req.predicted_monthly_savings_usd,
        verified_monthly_savings_usd=req.verified_monthly_savings_usd,
        target_service=req.target_service,
        confidence_calibration_factor=req.confidence_calibration_factor,
        variance_discount_pct=req.variance_discount_pct,
    )


@router.get("/attribution/summary", response_model=PortfolioSavingsSummary)
def get_portfolio_savings_summary() -> PortfolioSavingsSummary:
    """Get portfolio-wide aggregated savings metrics."""
    return get_savings_attribution_engine().get_portfolio_summary()


@router.get("/incidents", response_model=List[PostExecutionIncident])
def list_incidents() -> List[PostExecutionIncident]:
    """List all detected post-execution incidents."""
    return get_incident_detector().list_incidents()


@router.post("/learning/feedback", response_model=LearningUpdateReport)
def ingest_feedback(req: IngestFeedbackRequest) -> LearningUpdateReport:
    """Ingest human override or rejection into M8 learning pipeline."""
    bridge = get_learning_loop_bridge()
    if req.feedback_type.upper() == "OVERRIDE":
        return bridge.ingest_human_override(
            action_id=req.action_id,
            target_resource_id=req.target_resource_id,
            action=req.action,
            approver=req.actor,
            override_reason=req.reason,
        )
    elif req.feedback_type.upper() == "REJECTION":
        return bridge.ingest_rejection(
            action_id=req.action_id,
            target_resource_id=req.target_resource_id,
            action=req.action,
            rejected_by=req.actor,
            rejection_reason=req.reason,
        )
    else:
        raise HTTPException(status_code=400, detail="feedback_type must be 'OVERRIDE' or 'REJECTION'")


@router.get("/learning/metrics")
def get_learning_metrics() -> Dict[str, Any]:
    """Get continuous learning metrics, accuracy, and Cloud DNA profile."""
    bridge = get_learning_loop_bridge()
    return bridge.get_continuous_improvement_metrics()
