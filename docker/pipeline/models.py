"""
Unified Execution Context & Pipeline Data Models.

Defines schemas for the CloudPilot Intelligence Pipeline:
- Pipeline & Stage Statuses
- Stage Results, Errors, & Evidence
- Timeline Auditing Events
- Stage Outputs (M1 through M9)
- Ground Truth Benchmark Evaluation Reports
- UnifiedExecutionContext
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from models_resource import ResourceGraph
from models_cost import BillingLineItem, CostEvent, CostAnomaly, CostForecast
from models_application import ApplicationGraph
from models_risk import RiskAssessment
from models_strategy import OptimizationPlan, StrategyPortfolio, RoadmapPhase
from models_simulation import SimulationReport
from models_explanation import ExplanationReport, AuditTrail
from models_learning import CloudDNAProfile, PatternRecord, LearningMetrics
from models_decision import DecisionRecord, ConsensusResult, ExecutionPackage, AgentVote


class PipelineStatus(str, Enum):
    """Execution status of the overall intelligence pipeline."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


class StageStatus(str, Enum):
    """Execution status of an individual intelligence stage."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    DEGRADED = "DEGRADED"


class StageResult(BaseModel):
    """Structured report returned by every pipeline stage."""
    stage_id: str = Field(..., description="Unique stage identifier, e.g., 'm1_discovery'")
    stage_name: str = Field(..., description="Human-readable stage title")
    status: StageStatus = Field(default=StageStatus.PENDING)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = Field(default=0.0, ge=0.0, description="Execution duration in milliseconds")
    confidence: float = Field(default=100.0, ge=0.0, le=100.0, description="Stage confidence score (0-100%)")
    input_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of input artifacts consumed")
    output_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of output artifacts produced")
    errors: List[str] = Field(default_factory=list, description="Any warnings or errors captured during execution")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Structured supporting metrics & proof points")

    class Config:
        arbitrary_types_allowed = True


class TimelineEvent(BaseModel):
    """Auditable event log entry in the execution timeline."""
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:10]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stage_id: Optional[str] = None
    agent_name: str = Field(..., description="Module/agent emitting event")
    action: str = Field(..., description="Action performed, e.g., 'DISCOVERY_STARTED'")
    status: str = Field(default="INFO", description="INFO, SUCCESS, WARNING, ERROR")
    details: Dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Stage-Specific Structured Outputs
# ═══════════════════════════════════════════════════════════════

class CostStageOutput(BaseModel):
    """M2 Cost Intelligence structured output."""
    billing_items: List[BillingLineItem] = Field(default_factory=list)
    cost_events: List[CostEvent] = Field(default_factory=list)
    anomalies: List[CostAnomaly] = Field(default_factory=list)
    forecasts: List[CostForecast] = Field(default_factory=list)
    total_monthly_spend_usd: float = 0.0

    class Config:
        arbitrary_types_allowed = True


class RiskStageOutput(BaseModel):
    """M4 Risk Intelligence structured output."""
    assessments: Dict[str, RiskAssessment] = Field(default_factory=dict, description="target_id -> RiskAssessment")
    critical_risks_count: int = 0
    high_risks_count: int = 0
    overall_risk_category: str = "LOW"
    blast_radii: Dict[str, List[str]] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class StrategyStageOutput(BaseModel):
    """M5 Strategy Agent structured output."""
    plans: List[OptimizationPlan] = Field(default_factory=list)
    portfolio: Optional[StrategyPortfolio] = None
    roadmap: List[RoadmapPhase] = Field(default_factory=list)
    total_potential_savings_monthly_usd: float = 0.0

    class Config:
        arbitrary_types_allowed = True


class DigitalTwinStageOutput(BaseModel):
    """M6 Digital Twin simulation output."""
    twin_id: Optional[str] = None
    simulation_reports: Dict[str, SimulationReport] = Field(default_factory=dict, description="plan_id -> SimulationReport")
    average_safety_score: float = 100.0
    average_execution_readiness: float = 100.0

    class Config:
        arbitrary_types_allowed = True


class ExplainabilityStageOutput(BaseModel):
    """M7 Explainability structured output."""
    explanations: Dict[str, ExplanationReport] = Field(default_factory=dict, description="plan_id -> ExplanationReport")
    audit_trails: List[AuditTrail] = Field(default_factory=list)
    average_confidence: float = 100.0

    class Config:
        arbitrary_types_allowed = True


class LearningStageOutput(BaseModel):
    """M8 Learning structured output."""
    cloud_dna: Optional[CloudDNAProfile] = None
    detected_patterns: List[PatternRecord] = Field(default_factory=list)
    metrics: Optional[LearningMetrics] = None

    class Config:
        arbitrary_types_allowed = True


class DecisionStageOutput(BaseModel):
    """M9 Decision Engine structured output."""
    decisions: Dict[str, DecisionRecord] = Field(default_factory=dict, description="plan_id -> DecisionRecord")
    consensus_results: Dict[str, ConsensusResult] = Field(default_factory=dict)
    execution_packages: List[ExecutionPackage] = Field(default_factory=list)
    agent_votes: Dict[str, List[AgentVote]] = Field(default_factory=dict)
    approved_count: int = 0
    rejected_count: int = 0
    escalated_count: int = 0

    class Config:
        arbitrary_types_allowed = True


# ═══════════════════════════════════════════════════════════════
# Ground Truth Benchmark Evaluation Model
# ═══════════════════════════════════════════════════════════════

class PipelineEvaluationReport(BaseModel):
    """Benchmark evaluation comparing pipeline outputs against simulator Ground Truth."""
    evaluation_id: str = Field(default_factory=lambda: f"eval-{uuid.uuid4().hex[:10]}")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recommendation_precision: float = Field(..., ge=0.0, le=100.0, description="Precision % of recommended actions")
    recommendation_recall: float = Field(..., ge=0.0, le=100.0, description="Recall % of ground truth opportunities")
    savings_prediction_accuracy: float = Field(..., ge=0.0, le=100.0, description="Predicted vs true savings accuracy %")
    risk_prediction_accuracy: float = Field(..., ge=0.0, le=100.0, description="Risk classification accuracy %")
    simulation_accuracy: float = Field(..., ge=0.0, le=100.0, description="Digital twin safety prediction accuracy %")
    decision_accuracy: float = Field(..., ge=0.0, le=100.0, description="Final decision accuracy %")
    composite_score: float = Field(..., ge=0.0, le=100.0, description="Overall pipeline intelligence score (0-100)")
    regret_monthly_usd: float = Field(default=0.0, ge=0.0, description="Unrealized optimal savings ($/mo)")
    false_positives: List[str] = Field(default_factory=list, description="Actions recommended that were unsafe")
    false_negatives: List[str] = Field(default_factory=list, description="Safe opportunities missed")
    incidents_avoided: int = 0


# ═══════════════════════════════════════════════════════════════
# Master Unified Execution Context
# ═══════════════════════════════════════════════════════════════

class UnifiedExecutionContext(BaseModel):
    """
    Unified Execution Context for the CloudPilot Intelligence Pipeline.
    Maintains complete state across all 9 intelligence modules (M1-M9).
    """
    run_id: str = Field(default_factory=lambda: f"run-{uuid.uuid4().hex[:12]}")
    scenario_name: str
    scale: str = "small"
    seed: int = 42
    status: PipelineStatus = Field(default=PipelineStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_ms: float = 0.0

    # Structured Module States (M1 - M9)
    infrastructure_state: Optional[ResourceGraph] = None
    costs: Optional[CostStageOutput] = None
    applications: Optional[ApplicationGraph] = None
    risks: Optional[RiskStageOutput] = None
    strategies: Optional[StrategyStageOutput] = None
    simulations: Optional[DigitalTwinStageOutput] = None
    explanations: Optional[ExplainabilityStageOutput] = None
    historical_knowledge: Optional[LearningStageOutput] = None
    decision_state: Optional[DecisionStageOutput] = None

    # Pipeline Execution Metadata
    stage_results: Dict[str, StageResult] = Field(default_factory=dict)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    ground_truth_evaluation: Optional[PipelineEvaluationReport] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

    def add_timeline_event(
        self,
        agent_name: str,
        action: str,
        status: str = "INFO",
        stage_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> TimelineEvent:
        """Append an auditable event to the execution timeline."""
        evt = TimelineEvent(
            stage_id=stage_id,
            agent_name=agent_name,
            action=action,
            status=status,
            details=details or {}
        )
        self.timeline.append(evt)
        return evt
