"""
Base Stage Interface for CloudPilot Intelligence Pipeline.
Provides standardized execution envelopes, timing, error capture, retries, and cancellation handling.
"""

from __future__ import annotations

import abc
import logging
import time
from datetime import datetime, timezone
import threading
from typing import Any, Dict, Optional

from pipeline.models import StageResult, StageStatus, UnifiedExecutionContext

logger = logging.getLogger("cloudpilot.pipeline")


class BasePipelineStage(abc.ABC):
    """
    Abstract base class for an intelligence pipeline stage.
    Encapsulates lifecycle, telemetry timing, error handling, retries, and evidence capture.
    """

    stage_id: str = "base_stage"
    stage_name: str = "Base Stage"
    is_critical: bool = True
    max_retries: int = 1
    retry_delay_seconds: float = 0.2

    def __init__(self, is_critical: Optional[bool] = None, max_retries: Optional[int] = None) -> None:
        if is_critical is not None:
            self.is_critical = is_critical
        if max_retries is not None:
            self.max_retries = max_retries

    @abc.abstractmethod
    def _run(self, context: UnifiedExecutionContext) -> StageResult:
        """
        Subclass implementation of the stage logic.
        Must mutate the context as needed and return StageResult.
        """
        raise NotImplementedError

    def execute(
        self,
        context: UnifiedExecutionContext,
        cancel_token: Optional[threading.Event] = None
    ) -> StageResult:
        """
        Execute stage with full lifecycle envelope, retries, cancellation check, and timing.
        """
        if cancel_token and cancel_token.is_set():
            logger.warning("Stage %s cancelled before starting", self.stage_id)
            res = StageResult(
                stage_id=self.stage_id,
                stage_name=self.stage_name,
                status=StageStatus.SKIPPED,
                errors=["Cancelled before start"],
            )
            context.stage_results[self.stage_id] = res
            return res

        start_time = time.perf_counter()
        started_at = datetime.now(timezone.utc)
        context.add_timeline_event(
            agent_name=self.stage_name,
            action=f"{self.stage_id.upper()}_STARTED",
            status="INFO",
            stage_id=self.stage_id,
        )

        attempts = 0
        last_error = ""
        stage_result: Optional[StageResult] = None

        while attempts <= self.max_retries:
            attempts += 1
            if cancel_token and cancel_token.is_set():
                res = StageResult(
                    stage_id=self.stage_id,
                    stage_name=self.stage_name,
                    status=StageStatus.SKIPPED,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    errors=["Execution cancelled"],
                )
                context.stage_results[self.stage_id] = res
                return res

            try:
                stage_result = self._run(context)
                stage_result.started_at = started_at
                stage_result.completed_at = datetime.now(timezone.utc)
                stage_result.duration_ms = (time.perf_counter() - start_time) * 1000
                context.stage_results[self.stage_id] = stage_result

                context.add_timeline_event(
                    agent_name=self.stage_name,
                    action=f"{self.stage_id.upper()}_COMPLETED",
                    status="SUCCESS" if stage_result.status == StageStatus.COMPLETED else "WARNING",
                    stage_id=self.stage_id,
                    details=stage_result.output_summary,
                )
                return stage_result
            except Exception as exc:
                last_error = f"Attempt {attempts} failed: {exc}"
                logger.error("Stage [%s] error on attempt %d: %s", self.stage_id, attempts, exc, exc_info=True)
                if attempts <= self.max_retries:
                    time.sleep(self.retry_delay_seconds)

        # Exhausted retries
        duration_ms = (time.perf_counter() - start_time) * 1000
        status = StageStatus.FAILED if self.is_critical else StageStatus.DEGRADED
        failed_result = StageResult(
            stage_id=self.stage_id,
            stage_name=self.stage_name,
            status=status,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            duration_ms=duration_ms,
            confidence=0.0,
            errors=[last_error],
        )
        context.stage_results[self.stage_id] = failed_result

        context.add_timeline_event(
            agent_name=self.stage_name,
            action=f"{self.stage_id.upper()}_FAILED",
            status="ERROR",
            stage_id=self.stage_id,
            details={"error": last_error, "critical": self.is_critical},
        )
        return failed_result
