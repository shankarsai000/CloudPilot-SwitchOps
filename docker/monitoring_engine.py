"""
Monitoring Engine Component

Monitors target resource metrics (CPU, Memory, Network, Error Rate, Latency) during
and immediately after execution to detect anomalies or SLA violations.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from provider_router import ProviderRouter

logger = logging.getLogger(__name__)


class MonitoringEngine:
    """Monitors active and post-execution telemetry metrics."""

    def __init__(
        self,
        provider_router: Optional[ProviderRouter] = None,
        max_cpu_percent: float = 90.0,
        max_memory_percent: float = 90.0,
        max_error_rate: float = 0.05,
        max_latency_ms: float = 800.0,
    ) -> None:
        """Initialize Monitoring Engine with SLA thresholds."""
        self.router = provider_router or ProviderRouter()
        self.max_cpu_percent = max_cpu_percent
        self.max_memory_percent = max_memory_percent
        self.max_error_rate = max_error_rate
        self.max_latency_ms = max_latency_ms

    def collect_metrics(self, target_id: str, provider: str = "AWS") -> dict[str, Any] :
        """Collect live metrics for a target using provider adapters.

        Args:
            target_id: Target resource or application
            provider: Provider name

        Returns:
            Dict containing collected metrics
        """
        plan = {"target_id": target_id, "provider": provider}
        raw = self.router.monitor(plan)

        # Standardize metric mappings
        cpu = raw.get("CPUUtilization") or raw.get("Percentage CPU") or raw.get("instance/cpu/utilization", 0.0)
        # Handle GCP fraction CPU
        if cpu <= 1.0 and "cpu" in str(raw):
            cpu = cpu * 100.0

        memory = raw.get("pod/memory/usage") or raw.get("Percentage Memory", 45.0)

        # Synthetic metric generators
        metrics = {
            "cpu_percent": round(float(cpu), 2),
            "memory_percent": round(float(memory), 2),
            "error_rate": raw.get("error_rate", 0.01),
            "latency_ms": raw.get("latency_ms", 120.0),
            "availability": raw.get("availability", 1.0),
            "cost_per_hour": raw.get("cost_per_hour", 0.15),
            "raw": raw,
        }
        return metrics

    def detect_anomaly(self, metrics: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Inspect telemetry for SLA or performance anomalies.

        Args:
            metrics: Telemetry dataset

        Returns:
            Tuple of (is_anomaly, reason)
        """
        cpu = metrics.get("cpu_percent", 0.0)
        error_rate = metrics.get("error_rate", 0.0)
        latency = metrics.get("latency_ms", 0.0)

        if cpu > self.max_cpu_percent:
            return True, f"CPU utilization high: {cpu}% (threshold: {self.max_cpu_percent}%)"

        if error_rate > self.max_error_rate:
            return True, f"Error rate high: {error_rate * 100}% (threshold: {self.max_error_rate * 100}%)"

        if latency > self.max_latency_ms:
            return True, f"Latency spike: {latency}ms (threshold: {self.max_latency_ms}ms)"

        if metrics.get("availability", 1.0) < 0.99:
            return True, "Availability dropped below 99% SLA"

        return False, None
