"""
Digital Twin Simulation (M6-DTS) - Models

Defines the structure for virtual representation models, simulations, performance,
costs, safety scores, and comparisons.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PerformanceForecast(BaseModel):
    """Predicted resource utilization and response times."""

    cpu_utilization: float = Field(..., ge=0.0, le=100.0, description="Predicted CPU %")
    memory_utilization: float = Field(..., ge=0.0, le=100.0, description="Predicted Memory %")
    latency_ms: float = Field(..., ge=0.0, description="Predicted latency in ms")
    throughput_rps: float = Field(..., ge=0.0, description="Predicted requests per second")
    error_rate: float = Field(..., ge=0.0, le=1.0, description="Predicted error rate (0-1)")
    availability_percentage: float = Field(..., ge=0.0, le=100.0, description="Predicted uptime %")


class CostForecast(BaseModel):
    """Projections of billing modifications and transition costs."""

    immediate_savings_usd: float = Field(..., ge=0.0, description="One-time savings")
    monthly_savings_usd: float = Field(..., ge=0.0, description="Monthly recurring savings")
    migration_cost_usd: float = Field(..., ge=0.0, description="One-time effort transition expenses")
    future_bill_monthly_usd: float = Field(..., ge=0.0, description="Forecasted monthly cloud bill")


class RollbackReport(BaseModel):
    """Timeline and complexity estimations for recovery configurations."""

    rollback_duration_minutes: float = Field(..., ge=0.0, description="Estimated time to revert")
    rollback_complexity: str = Field(..., description="Complexity scale: LOW, MEDIUM, HIGH")
    rollback_probability_percentage: float = Field(..., ge=0.0, le=100.0, description="Likelihood of failure triggering rollback")
    recovery_confidence_percentage: float = Field(..., ge=0.0, le=100.0, description="Confidence in recovery success")


class DigitalTwin(BaseModel):
    """Virtual representation containing state representations for simulation runs."""

    twin_id: str = Field(..., description="Unique digital twin state ID")
    resources: list[dict[str, Any]] = Field(default_factory=list, description="State of resources")
    applications: list[dict[str, Any]] = Field(default_factory=list, description="State of applications")
    cost_model: dict[str, Any] = Field(default_factory=dict, description="Pre-simulated cost details")
    dependency_graph: dict[str, Any] = Field(default_factory=dict, description="Mapped topology dependencies")
    policies: list[dict[str, Any]] = Field(default_factory=list, description="Organization policies active")
    snapshot_time: datetime = Field(default_factory=datetime.utcnow)


class SimulationReport(BaseModel):
    """Aggregated predictions for simulated actions."""

    simulation_id: str = Field(..., description="Unique simulation run identifier")
    target_id: str = Field(..., description="Resource or Application ID simulated")
    action: str = Field(..., description="Action simulated")
    safety_score: float = Field(..., ge=0.0, le=100.0, description="Safety rating (0-100)")
    safety_status: str = Field(..., description="Safe, Unsafe, Requires Approval")
    performance: PerformanceForecast = Field(..., description="Predicted performance forecast")
    cost: CostForecast = Field(..., description="Predicted cost forecast")
    rollback: RollbackReport = Field(..., description="Estimated rollback prediction report")
    cascading_failures: list[str] = Field(default_factory=list, description="Cascading failure paths predicted")
    execution_readiness_score: float = Field(..., ge=0.0, le=100.0, description="Readiness score")
    simulated_at: datetime = Field(default_factory=datetime.utcnow)


class ScenarioComparison(BaseModel):
    """Side-by-side strategy evaluations with recommendations."""

    comparison_id: str = Field(..., description="Unique comparison matrix ID")
    target_id: str = Field(...)
    base_state: dict[str, Any] = Field(..., description="Baseline costs and performance metrics")
    simulations: dict[str, SimulationReport] = Field(..., description="Strategy name -> Simulation report")
    recommended_strategy_name: str = Field(..., description="Best candidate strategy based on score balance")
    trade_off_analysis: str = Field(..., description="Analysis summarizing outcomes")
