"""
Performance Predictor Component

Estimates CPU, memory, latency, throughput, error rate, and availability
metrics based on simulated actions and twin workloads.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from models_simulation import PerformanceForecast

logger = logging.getLogger(__name__)


class PerformancePredictor:
    """Predicts performance degradation or gains for hypothetical configuration adjustments."""

    def __init__(self) -> None:
        """Initialize Performance Predictor."""
        pass

    def predict_performance(
        self,
        target_id: str,
        action: str,
        parameters: dict[str, Any],
        twin_context: Any
    ) -> PerformanceForecast:
        """Estimate metrics details.

        Args:
            target_id: Target resource/application ID
            action: Action simulated
            parameters: Action parameters
            twin_context: Mapped twin state details

        Returns:
            PerformanceForecast object
        """
        # Baseline normal running values
        cpu = 45.0
        mem = 60.0
        latency = 15.0
        throughput = 250.0
        error_rate = 0.001
        availability = 99.99

        # Find target in twin resource states
        res_data = next((r for r in twin_context.resources if r["id"] == target_id), None)
        if res_data:
            metadata = res_data.get("metadata", {})
            cpu = float(metadata.get("cpu_utilization", 45.0))
            mem = float(metadata.get("memory_utilization", 60.0))
            latency = float(metadata.get("latency_ms", 15.0))

        if action == "TERMINATE":
            cpu = 0.0
            mem = 0.0
            latency = 1000.0  # infinite latency
            throughput = 0.0
            error_rate = 1.0  # 100% failure
            availability = 0.0

        elif action == "STOP":
            cpu = 0.0
            mem = 0.0
            latency = 1000.0
            throughput = 0.0
            error_rate = 1.0
            availability = 0.0

        elif action == "RESIZE":
            # Shrinking size increases CPU/memory metrics load but saves cost
            resize_to = parameters.get("resize_to", "smaller")
            if "smaller" in resize_to.lower() or "t3" in resize_to.lower():
                cpu = min(cpu * 1.8, 90.0)
                mem = min(mem * 1.5, 95.0)
                latency = latency * 1.4
                error_rate = min(error_rate * 2.0, 0.01)

        elif action == "RESTART":
            # Temporary availability drop
            availability = 99.0
            latency = latency * 10.0

        return PerformanceForecast(
            cpu_utilization=round(cpu, 1),
            memory_utilization=round(mem, 1),
            latency_ms=round(latency, 2),
            throughput_rps=round(throughput, 1),
            error_rate=round(error_rate, 4),
            availability_percentage=round(availability, 2)
        )
