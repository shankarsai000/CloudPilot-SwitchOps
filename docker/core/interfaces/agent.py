"""
Base Agent Interface and Lifecycle Contracts.
"""

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.observability.metrics import get_metrics_collector


class AgentStatus(str, Enum):
    """Runtime status of an agent."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    ERROR = "error"
    DEGRADED = "degraded"


class AgentMetadata(BaseModel):
    """Identification and capability metadata for an agent."""
    module_id: str = Field(description="Unique module identifier (e.g. M1, M2, M9)")
    name: str = Field(description="Human-readable agent name")
    version: str = Field(default="1.0.0", description="Agent version")
    description: str = Field(default="", description="Agent responsibilities summary")
    capabilities: List[str] = Field(default_factory=list, description="List of supported operations")


class AgentExecutionResult(BaseModel):
    """Standardized response envelope returned by any agent execution."""
    success: bool
    data: Optional[Any] = None
    execution_time_ms: float = Field(default=0.0)
    message: str = Field(default="Execution completed successfully")
    errors: List[str] = Field(default_factory=list)


class BaseAgent(ABC):
    """
    Abstract contract for all CloudPilot AI specialized agents (M1 to M10).
    Guarantees standard lifecycle management, metrics recording, and health monitoring.
    """

    def __init__(self, metadata: AgentMetadata) -> None:
        self._metadata = metadata
        self._status = AgentStatus.IDLE

    @property
    def metadata(self) -> AgentMetadata:
        """Return agent metadata."""
        return self._metadata

    @property
    def status(self) -> AgentStatus:
        """Return current agent status."""
        return self._status

    def initialize(self) -> None:
        """Perform startup initialization and resource allocation."""
        self._status = AgentStatus.READY

    def shutdown(self) -> None:
        """Perform graceful cleanup and release connections."""
        self._status = AgentStatus.IDLE

    def health_check(self) -> bool:
        """Verify internal state and external dependencies connectivity."""
        return self._status in (AgentStatus.READY, AgentStatus.IDLE, AgentStatus.RUNNING)

    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentExecutionResult:
        """
        Public execution wrapper with timing and metrics recording.
        Delegates core logic to _execute().
        """
        start = time.perf_counter()
        self._status = AgentStatus.RUNNING
        metrics = get_metrics_collector()

        try:
            result = self._execute(context or {})
            elapsed = (time.perf_counter() - start) * 1000.0
            result.execution_time_ms = round(elapsed, 2)
            self._status = AgentStatus.READY if result.success else AgentStatus.ERROR
            metrics.record_agent_execution(self._metadata.module_id, "success" if result.success else "failure")
            return result
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            self._status = AgentStatus.ERROR
            metrics.record_agent_execution(self._metadata.module_id, "error")
            return AgentExecutionResult(
                success=False,
                data=None,
                execution_time_ms=round(elapsed, 2),
                message=f"Agent execution failed: {exc}",
                errors=[str(exc)],
            )

    @abstractmethod
    def _execute(self, context: Dict[str, Any]) -> AgentExecutionResult:
        """Concrete agent execution logic implemented by subclasses."""
        pass
