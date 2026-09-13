"""
Typed event models for inter-module messaging.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from core.logging import get_correlation_id


class EventType(str, Enum):
    """Core platform event types emitted across modules M1 through M10."""
    RESOURCE_DISCOVERED = "discovery.resource.discovered"
    DISCOVERY_COMPLETED = "discovery.cycle.completed"

    COST_EVENT_INGESTED = "cost.event.ingested"
    COST_ANOMALY_DETECTED = "cost.anomaly.detected"

    APPLICATION_DISCOVERED = "application.discovered"
    TOPOLOGY_UPDATED = "application.topology.updated"

    RISK_ASSESSED = "risk.assessment.completed"
    BLAST_RADIUS_COMPUTED = "risk.blast_radius.computed"

    STRATEGY_GENERATED = "strategy.recommendations.generated"
    SIMULATION_COMPLETED = "digital_twin.simulation.completed"

    DECISION_PROPOSED = "decision.proposed"
    DECISION_APPROVED = "decision.approved"
    DECISION_REJECTED = "decision.rejected"

    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_ROLLED_BACK = "execution.rolled_back"


class BaseEvent(BaseModel):
    """Universal event envelope for all published system events."""
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    event_type: str = Field(description="Dotted event topic identifier")
    source_module: str = Field(description="Module name that produced this event (e.g. M1, M2)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = Field(default_factory=get_correlation_id)
    payload: Dict[str, Any] = Field(default_factory=dict, description="Typed event payload data")
