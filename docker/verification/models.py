"""
Outcome Verification, Deterministic Rollback, Savings Attribution, & Learning Loop Models.

Defines schemas for:
- 5-Dimensional Expected vs Actual Outcomes (Cost, Performance, Availability, Risk, Savings)
- Outcome Reports & Safety Threshold Breaches
- Deterministic & Idempotent Rollback Plans and Results
- 3-Way Savings Attribution (Predicted, Verified, Annualized)
- Post-Execution Incidents
- M8 Learning Loop Ingestion Records
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════

class OutcomeVerdict(str, Enum):
    """Overall verdict of post-execution outcome verification."""
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"          # Met or exceeded all expectations within thresholds
    ACCEPTABLE_DEVIATION = "ACCEPTABLE_DEVIATION"  # Minor variance within tolerable bounds
    THRESHOLD_BREACH = "THRESHOLD_BREACH"          # Violates configured safety thresholds -> triggers rollback
    EXECUTION_FAILED = "EXECUTION_FAILED"          # Action failed to apply
    ROLLED_BACK = "ROLLED_BACK"                    # Rollback successfully executed


class IncidentSeverity(str, Enum):
    """Severity classification for post-execution incidents."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class OutcomeDimension(str, Enum):
    """The 5 evaluation dimensions."""
    COST = "COST"
    PERFORMANCE = "PERFORMANCE"
    AVAILABILITY = "AVAILABILITY"
    RISK = "RISK"
    SAVINGS = "SAVINGS"


# ═══════════════════════════════════════════════════════════════
# Safety Thresholds & Outcomes
# ═══════════════════════════════════════════════════════════════

class SafetyThresholds(BaseModel):
    """Configurable tolerance boundaries before triggering automated rollback."""
    max_latency_increase_pct: float = Field(20.0, description="Max allowed p99 latency increase percentage")
    max_latency_absolute_ms: float = Field(250.0, description="Hard ceiling for p99 latency")
    min_availability_pct: float = Field(99.9, description="Minimum acceptable availability percentage")
    max_cost_overshoot_pct: float = Field(15.0, description="Max allowed cost overshoot above expected")
    max_cpu_utilization_pct: float = Field(85.0, description="Max allowed post-action CPU utilization")
    min_savings_realization_pct: float = Field(50.0, description="Min allowed % of predicted savings realized")


class ExpectedOutcome(BaseModel):
    """
    Ex-ante expectations generated before executing an infrastructure modification.
    Encompasses the 5 required dimensions:
    1. Cost
    2. Performance
    3. Availability
    4. Risk
    5. Savings
    """
    action_id: str
    target_resource_id: str
    target_service: str = "unknown"

    # Dimension 1: Cost
    baseline_monthly_cost_usd: float
    expected_monthly_cost_usd: float

    # Dimension 2: Performance
    expected_cpu_utilization_pct: float = 45.0
    expected_memory_headroom_pct: float = 40.0
    expected_latency_p99_ms: float = 45.0

    # Dimension 3: Availability
    expected_availability_pct: float = 99.99
    expected_error_rate_pct: float = 0.01

    # Dimension 4: Risk
    expected_risk_level: str = "LOW"
    expected_slo_risk_prob: float = 0.02

    # Dimension 5: Savings
    expected_monthly_savings_usd: float

    # Thresholds
    thresholds: SafetyThresholds = Field(default_factory=SafetyThresholds)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActualOutcome(BaseModel):
    """
    Ex-post empirical telemetry and cost metrics gathered after execution.
    """
    action_id: str
    target_resource_id: str

    # Dimension 1: Cost
    measured_monthly_cost_usd: float

    # Dimension 2: Performance
    measured_cpu_utilization_pct: float
    measured_memory_headroom_pct: float
    measured_latency_p99_ms: float

    # Dimension 3: Availability
    measured_availability_pct: float
    measured_error_rate_pct: float

    # Dimension 4: Risk
    measured_risk_level: str
    observed_incidents_count: int = 0

    # Dimension 5: Savings
    measured_monthly_savings_usd: float = 0.0
    measured_savings_usd: float = 0.0

    def model_post_init(self, __context: Any) -> None:
        if self.measured_savings_usd != 0.0 and self.measured_monthly_savings_usd == 0.0:
            self.measured_monthly_savings_usd = self.measured_savings_usd
        elif self.measured_monthly_savings_usd != 0.0 and self.measured_savings_usd == 0.0:
            self.measured_savings_usd = self.measured_monthly_savings_usd

    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OutcomeReport(BaseModel):
    """
    Comprehensive comparison of expected vs actual outcomes across all 5 dimensions.
    """
    report_id: str = Field(default_factory=lambda: f"rep-{uuid.uuid4().hex[:8]}")
    action_id: str
    target_resource_id: str
    expected: ExpectedOutcome
    actual: ActualOutcome

    # Calculated Variances & Deltas
    cost_variance_pct: float = Field(..., description="% difference between actual and expected cost")
    savings_realization_rate: float = Field(..., description="actual_savings / expected_savings")
    latency_increase_pct: float = Field(..., description="% increase in p99 latency")
    latency_delta_ms: float = Field(..., description="actual_latency - expected_latency")
    availability_drop_pct: float = Field(..., description="expected_avail - actual_avail")
    cpu_headroom_delta_pct: float

    # Verdict & Safety Gates
    verdict: OutcomeVerdict
    breached_thresholds: List[str] = Field(default_factory=list)
    rollback_required: bool = False
    details: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# Deterministic Rollback Models
# ═══════════════════════════════════════════════════════════════

class RollbackPlan(BaseModel):
    """Deterministic inverse operational plan."""
    rollback_id: str = Field(default_factory=lambda: f"rbk-{uuid.uuid4().hex[:8]}")
    action_id: str
    target_resource_id: str
    original_action_type: str
    inverse_action_type: str
    original_parameters: Dict[str, Any] = Field(default_factory=dict)
    inverse_parameters: Dict[str, Any] = Field(default_factory=dict)
    baseline_snapshot: Dict[str, Any] = Field(default_factory=dict)
    is_deterministic: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RollbackResult(BaseModel):
    """Outcome of an executed rollback."""
    rollback_id: str
    action_id: str
    target_resource_id: str
    status: str = Field("SUCCESS", description="'SUCCESS', 'FAILED', or 'ALREADY_ROLLED_BACK'")
    is_idempotent_replay: bool = False
    baseline_restored: bool = True
    pre_rollback_state: Dict[str, Any] = Field(default_factory=dict)
    post_rollback_state: Dict[str, Any] = Field(default_factory=dict)
    audit_record_id: Optional[str] = None
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: str = ""


# ═══════════════════════════════════════════════════════════════
# Savings Attribution Models
# ═══════════════════════════════════════════════════════════════

class SavingsAttribution(BaseModel):
    """
    Rigorous 3-way savings attribution:
    1. Predicted Savings (ex-ante estimate)
    2. Verified Savings (ex-post empirically verified billable delta)
    3. Annualized Savings (risk-calibrated 12-month run rate)
    """
    attribution_id: str = Field(default_factory=lambda: f"att-{uuid.uuid4().hex[:8]}")
    action_id: str
    target_resource_id: str
    target_service: str = "unknown"

    # 1. Predicted Savings
    predicted_monthly_savings_usd: float

    # 2. Verified Savings
    verified_monthly_savings_usd: float

    # 3. Annualized Savings
    annualized_savings_usd: float

    # Accuracy Metrics
    realization_percentage: float = Field(..., description="(verified / predicted) * 100")
    confidence_calibration_factor: float = Field(0.95, description="Confidence factor discount")
    variance_discount_pct: float = Field(0.05, description="Discount for operational variance")
    attributed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# Post-Execution Incident Models
# ═══════════════════════════════════════════════════════════════

class PostExecutionIncident(BaseModel):
    """Incident identified following an infrastructure modification."""
    incident_id: str = Field(default_factory=lambda: f"inc-{uuid.uuid4().hex[:8]}")
    action_id: str
    target_resource_id: str
    target_service: str
    severity: IncidentSeverity
    incident_type: str = Field(..., description="e.g. LATENCY_SPIKE, CPU_STARVATION, AVAILABILITY_DROP")
    description: str
    observed_metric: str
    observed_value: float
    threshold_value: float
    triggered_rollback: bool = False
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# Learning Loop Models
# ═══════════════════════════════════════════════════════════════

class LearningUpdateReport(BaseModel):
    """Summary of M8 learning ingestion and Cloud DNA evolution."""
    update_id: str = Field(default_factory=lambda: f"lup-{uuid.uuid4().hex[:8]}")
    action_id: str
    event_type: str
    outcome_type: str
    confidence_delta: float
    cloud_dna_version: str
    updated_metrics: Dict[str, float] = Field(default_factory=dict)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
