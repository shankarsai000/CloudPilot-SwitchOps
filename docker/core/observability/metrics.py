"""
Metrics collection and Prometheus-compatible metrics endpoint.
"""

import time
import threading
from collections import defaultdict
from typing import Any, Dict, Tuple
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class MetricsCollector:
    """Thread-safe collector for platform runtime metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._http_requests_total: Dict[Tuple[str, str, int], int] = defaultdict(int)
        self._http_duration_sum: Dict[Tuple[str, str], float] = defaultdict(float)
        self._http_duration_count: Dict[Tuple[str, str], int] = defaultdict(int)
        self._agent_executions_total: Dict[Tuple[str, str], int] = defaultdict(int)
        self._errors_total: Dict[str, int] = defaultdict(int)

    def record_http_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        """Record an incoming HTTP request execution."""
        clean_path = self._normalize_path(path)
        with self._lock:
            self._http_requests_total[(method, clean_path, status_code)] += 1
            self._http_duration_sum[(method, clean_path)] += duration_seconds
            self._http_duration_count[(method, clean_path)] += 1

    def record_agent_execution(self, agent_name: str, status: str) -> None:
        """Record an agent execution event."""
        with self._lock:
            self._agent_executions_total[(agent_name, status)] += 1

    def record_error(self, error_code: str) -> None:
        """Record an application domain error occurrence."""
        with self._lock:
            self._errors_total[error_code] += 1

    def _normalize_path(self, path: str) -> str:
        """Normalize high-cardinality paths to prevent metric explosion."""
        parts = path.strip("/").split("/")
        clean_parts = []
        for p in parts:
            # Replace UUID or resource IDs with placeholder
            if len(p) > 20 or any(char.isdigit() for char in p if len(p) > 8):
                clean_parts.append(":id")
            else:
                clean_parts.append(p)
        return "/" + "/".join(clean_parts) if clean_parts else "/"

    def render_prometheus(self) -> str:
        """Render all metrics in standard Prometheus exposition format."""
        lines = [
            "# HELP http_requests_total Total number of HTTP requests.",
            "# TYPE http_requests_total counter",
        ]
        with self._lock:
            for (method, path, status_code), count in self._http_requests_total.items():
                lines.append(f'http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')

            lines.append("# HELP http_request_duration_seconds Total time spent in HTTP requests.")
            lines.append("# TYPE http_request_duration_seconds counter")
            for (method, path), dur_sum in self._http_duration_sum.items():
                dur_count = self._http_duration_count.get((method, path), 1)
                lines.append(f'http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {dur_sum:.6f}')
                lines.append(f'http_request_duration_seconds_count{{method="{method}",path="{path}"}} {dur_count}')

            lines.append("# HELP agent_executions_total Total agent executions across modules.")
            lines.append("# TYPE agent_executions_total counter")
            for (agent, status), count in self._agent_executions_total.items():
                lines.append(f'agent_executions_total{{agent="{agent}",status="{status}"}} {count}')

            lines.append("# HELP platform_errors_total Total platform errors by code.")
            lines.append("# TYPE platform_errors_total counter")
            for code, count in self._errors_total.items():
                lines.append(f'platform_errors_total{{code="{code}"}} {count}')

        return "\n".join(lines) + "\n"

    def get_summary(self) -> Dict[str, Any]:
        """Return metrics as a structured JSON-serializable dictionary."""
        with self._lock:
            total_requests = sum(self._http_requests_total.values())
            total_errors = sum(self._errors_total.values())
            return {
                "total_http_requests": total_requests,
                "total_errors": total_errors,
                "agent_executions": {f"{k[0]}:{k[1]}": v for k, v in self._agent_executions_total.items()},
                "error_counts": dict(self._errors_total),
            }


_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Return the platform metrics collector singleton."""
    return _collector


class MetricsMiddleware(BaseHTTPMiddleware):
    """Measures latency and records status codes for every HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            # Don't record metrics endpoint itself
            if not request.url.path.endswith("/metrics"):
                _collector.record_http_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_seconds=duration,
                )
