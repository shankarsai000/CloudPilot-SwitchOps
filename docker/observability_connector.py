"""
Observability Connector — Monitoring system integration.

Adapter pattern for connecting to observability platforms
(Prometheus, Datadog, OpenTelemetry, etc.) to collect service
health metrics, distributed traces, and runtime telemetry.

All adapters use mocked data during development.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ServiceMetrics(BaseModel):
    """Runtime metrics for a service."""

    service_id: str = Field(..., description="Service identifier")
    health_status: str = Field(default="unknown", description="Health status")
    request_rate: float = Field(default=0.0, ge=0.0, description="Requests per second")
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Error rate")
    latency_p50_ms: float = Field(default=0.0, ge=0.0, description="p50 latency in ms")
    latency_p95_ms: float = Field(default=0.0, ge=0.0, description="p95 latency in ms")
    latency_p99_ms: float = Field(default=0.0, ge=0.0, description="p99 latency in ms")
    cpu_utilization: float = Field(default=0.0, ge=0.0, le=100.0, description="CPU %")
    memory_utilization: float = Field(default=0.0, ge=0.0, le=100.0, description="Memory %")
    saturation: float = Field(default=0.0, ge=0.0, le=1.0, description="Resource saturation")
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="Collection timestamp")
    source: str = Field(default="unknown", description="Observability source")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "service_id": "svc-payment-api",
                "health_status": "healthy",
                "request_rate": 450.0,
                "error_rate": 0.002,
                "latency_p50_ms": 12.5,
                "latency_p99_ms": 85.0,
                "cpu_utilization": 45.2,
                "memory_utilization": 62.8,
                "source": "prometheus",
            }
        }


class TraceSpan(BaseModel):
    """Single span from a distributed trace."""

    trace_id: str = Field(..., description="Trace identifier")
    span_id: str = Field(..., description="Span identifier")
    parent_span_id: Optional[str] = Field(None, description="Parent span ID")
    service_name: str = Field(..., description="Service name")
    operation_name: str = Field(..., description="Operation name")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Span duration in ms")
    status: str = Field(default="ok", description="Span status")
    start_time: datetime = Field(default_factory=datetime.utcnow, description="Start time")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "trace_id": "abc123",
                "span_id": "span-001",
                "service_name": "payment-api",
                "operation_name": "process_payment",
                "duration_ms": 45.0,
                "status": "ok",
            }
        }


class ObservabilityAdapter(ABC):
    """Abstract adapter for observability platform integration."""

    @abstractmethod
    def get_service_metrics(self, service_id: str) -> Optional[ServiceMetrics]:
        """Fetch current metrics for a service.

        Args:
            service_id: Service identifier

        Returns:
            ServiceMetrics or None if unavailable
        """
        ...

    @abstractmethod
    def get_traces(
        self, service_name: str, limit: int = 10
    ) -> list[TraceSpan]:
        """Fetch recent trace spans for a service.

        Args:
            service_name: Service name
            limit: Maximum spans to return

        Returns:
            List of TraceSpan objects
        """
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Observability platform name."""
        ...


class PrometheusAdapter(ObservabilityAdapter):
    """Prometheus/VictoriaMetrics observability adapter.

    Uses mocked data during development. In production, would
    query Prometheus HTTP API for metrics.
    """

    def __init__(self, endpoint: Optional[str] = None) -> None:
        """Initialize Prometheus adapter.

        Args:
            endpoint: Prometheus server endpoint URL
        """
        self._endpoint = endpoint
        logger.info("PrometheusAdapter initialized (endpoint=%s)", endpoint or "mock")

    @property
    def source_name(self) -> str:
        """Return adapter source name."""
        return "prometheus"

    def get_service_metrics(self, service_id: str) -> Optional[ServiceMetrics]:
        """Fetch metrics from Prometheus (mocked).

        Args:
            service_id: Service identifier

        Returns:
            Mocked ServiceMetrics
        """
        # In production: query Prometheus API
        # GET /api/v1/query?query=rate(http_requests_total{service="..."}[5m])
        return ServiceMetrics(
            service_id=service_id,
            health_status="healthy",
            request_rate=150.0,
            error_rate=0.005,
            latency_p50_ms=15.0,
            latency_p95_ms=45.0,
            latency_p99_ms=120.0,
            cpu_utilization=35.0,
            memory_utilization=55.0,
            saturation=0.35,
            source=self.source_name,
        )

    def get_traces(
        self, service_name: str, limit: int = 10
    ) -> list[TraceSpan]:
        """Prometheus does not provide traces.

        Args:
            service_name: Service name
            limit: Maximum spans

        Returns:
            Empty list (Prometheus has no tracing)
        """
        return []


class DatadogAdapter(ObservabilityAdapter):
    """Datadog observability adapter.

    Uses mocked data during development. In production, would
    use Datadog API for metrics and APM traces.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> None:
        """Initialize Datadog adapter.

        Args:
            api_key: Datadog API key
            app_key: Datadog application key
        """
        self._api_key = api_key
        self._app_key = app_key
        logger.info("DatadogAdapter initialized")

    @property
    def source_name(self) -> str:
        """Return adapter source name."""
        return "datadog"

    def get_service_metrics(self, service_id: str) -> Optional[ServiceMetrics]:
        """Fetch metrics from Datadog (mocked).

        Args:
            service_id: Service identifier

        Returns:
            Mocked ServiceMetrics
        """
        return ServiceMetrics(
            service_id=service_id,
            health_status="healthy",
            request_rate=200.0,
            error_rate=0.003,
            latency_p50_ms=10.0,
            latency_p95_ms=35.0,
            latency_p99_ms=90.0,
            cpu_utilization=40.0,
            memory_utilization=60.0,
            saturation=0.40,
            source=self.source_name,
        )

    def get_traces(
        self, service_name: str, limit: int = 10
    ) -> list[TraceSpan]:
        """Fetch APM traces from Datadog (mocked).

        Args:
            service_name: Service name
            limit: Maximum spans

        Returns:
            Mocked trace spans
        """
        return [
            TraceSpan(
                trace_id=f"dd-trace-{service_name}-001",
                span_id="dd-span-001",
                service_name=service_name,
                operation_name="http.request",
                duration_ms=25.0,
                status="ok",
            )
        ]


class GenericOTelAdapter(ObservabilityAdapter):
    """OpenTelemetry-compatible observability adapter.

    Generic adapter for any OTLP-compatible backend
    (Jaeger, Elastic APM, New Relic, etc.).
    Uses mocked data during development.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        backend_name: str = "opentelemetry",
    ) -> None:
        """Initialize OpenTelemetry adapter.

        Args:
            endpoint: OTLP endpoint URL
            backend_name: Backend system name (jaeger, elastic, newrelic)
        """
        self._endpoint = endpoint
        self._backend_name = backend_name
        logger.info(
            "GenericOTelAdapter initialized (backend=%s, endpoint=%s)",
            backend_name,
            endpoint or "mock",
        )

    @property
    def source_name(self) -> str:
        """Return adapter source name."""
        return self._backend_name

    def get_service_metrics(self, service_id: str) -> Optional[ServiceMetrics]:
        """Fetch metrics via OTLP (mocked).

        Args:
            service_id: Service identifier

        Returns:
            Mocked ServiceMetrics
        """
        return ServiceMetrics(
            service_id=service_id,
            health_status="healthy",
            request_rate=100.0,
            error_rate=0.01,
            latency_p50_ms=20.0,
            latency_p95_ms=60.0,
            latency_p99_ms=150.0,
            cpu_utilization=50.0,
            memory_utilization=65.0,
            saturation=0.50,
            source=self.source_name,
        )

    def get_traces(
        self, service_name: str, limit: int = 10
    ) -> list[TraceSpan]:
        """Fetch distributed traces via OTLP (mocked).

        Args:
            service_name: Service name
            limit: Maximum spans

        Returns:
            Mocked trace spans
        """
        spans: list[TraceSpan] = []
        for i in range(min(limit, 3)):
            spans.append(
                TraceSpan(
                    trace_id=f"otel-trace-{service_name}-{i:03d}",
                    span_id=f"otel-span-{i:03d}",
                    parent_span_id=f"otel-span-{i - 1:03d}" if i > 0 else None,
                    service_name=service_name,
                    operation_name=f"operation-{i}",
                    duration_ms=15.0 + i * 10,
                    status="ok",
                )
            )
        return spans


class ObservabilityConnector:
    """Multi-source observability connector.

    Manages multiple observability adapters and provides a unified
    interface for fetching service metrics and traces. Uses the
    Adapter pattern for extensibility.
    """

    def __init__(
        self,
        adapters: Optional[list[ObservabilityAdapter]] = None,
    ) -> None:
        """Initialize observability connector.

        Args:
            adapters: List of observability adapters (defaults to all mock adapters)
        """
        self._adapters: list[ObservabilityAdapter] = adapters or [
            PrometheusAdapter(),
        ]
        logger.info(
            "ObservabilityConnector initialized with %d adapters: %s",
            len(self._adapters),
            [a.source_name for a in self._adapters],
        )

    def add_adapter(self, adapter: ObservabilityAdapter) -> None:
        """Register an observability adapter.

        Args:
            adapter: Adapter to register
        """
        self._adapters.append(adapter)
        logger.info("Registered observability adapter: %s", adapter.source_name)

    def get_service_metrics(self, service_id: str) -> Optional[ServiceMetrics]:
        """Fetch metrics from the first available adapter.

        Tries adapters in order, returns first successful result.

        Args:
            service_id: Service identifier

        Returns:
            ServiceMetrics or None if all adapters fail
        """
        for adapter in self._adapters:
            try:
                metrics = adapter.get_service_metrics(service_id)
                if metrics:
                    return metrics
            except Exception as e:
                logger.warning(
                    "Adapter %s failed for %s: %s",
                    adapter.source_name,
                    service_id,
                    e,
                )
        return None

    def get_all_metrics(self, service_id: str) -> list[ServiceMetrics]:
        """Fetch metrics from all adapters.

        Args:
            service_id: Service identifier

        Returns:
            List of ServiceMetrics from all adapters
        """
        results: list[ServiceMetrics] = []
        for adapter in self._adapters:
            try:
                metrics = adapter.get_service_metrics(service_id)
                if metrics:
                    results.append(metrics)
            except Exception as e:
                logger.warning(
                    "Adapter %s failed for %s: %s",
                    adapter.source_name,
                    service_id,
                    e,
                )
        return results

    def get_traces(
        self, service_name: str, limit: int = 10
    ) -> list[TraceSpan]:
        """Fetch traces from all adapters.

        Args:
            service_name: Service name
            limit: Maximum spans per adapter

        Returns:
            Combined list of TraceSpan objects
        """
        all_spans: list[TraceSpan] = []
        for adapter in self._adapters:
            try:
                spans = adapter.get_traces(service_name, limit)
                all_spans.extend(spans)
            except Exception as e:
                logger.warning(
                    "Adapter %s trace fetch failed for %s: %s",
                    adapter.source_name,
                    service_name,
                    e,
                )
        return all_spans

    def get_adapter_status(self) -> dict[str, str]:
        """Get status of all registered adapters.

        Returns:
            Dict mapping adapter name → status
        """
        return {
            adapter.source_name: "connected" for adapter in self._adapters
        }
