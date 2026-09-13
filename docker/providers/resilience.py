"""
Resilience Engine: Token Bucket Rate Limiting, Circuit Breakers, Exponential Backoff Retries, and Tracing.
"""

from __future__ import annotations

import logging
import random
import secrets
import time
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

from providers.models import (
    CloudProvider,
    ProviderError,
    ProviderRateLimitError,
    ProviderTransientError,
)

logger = logging.getLogger("cloudpilot.providers.resilience")

T = TypeVar("T")


class CircuitBreakerState(str, Enum):
    """States for circuit breaker pattern."""
    CLOSED = "CLOSED"        # Normal operation: requests pass through
    OPEN = "OPEN"            # Provider degraded: fast-fail calls
    HALF_OPEN = "HALF_OPEN"  # Testing recovery with limited traffic


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter tracking requests per provider/service.
    Enforces smooth rate limiting with burst tolerance.
    """

    def __init__(
        self,
        provider: CloudProvider,
        capacity: float = 60.0,
        refill_rate: float = 20.0,  # tokens per second
    ) -> None:
        self.provider = provider
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self.total_throttled = 0

    def _refill(self) -> None:
        """Add tokens earned based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    def acquire(self, tokens: float = 1.0, wait: bool = False, timeout: float = 1.0) -> bool:
        """
        Attempt to acquire tokens.
        If unavailable and wait=False, raises ProviderRateLimitError.
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        # Needs wait or fast-fail
        deficit = tokens - self.tokens
        wait_seconds = deficit / self.refill_rate if self.refill_rate > 0 else 1.0

        if not wait or wait_seconds > timeout:
            self.total_throttled += 1
            raise ProviderRateLimitError(
                provider=self.provider,
                message=f"Rate limit exceeded for provider {self.provider.value}. Wait {wait_seconds:.2f}s",
                retry_after_seconds=round(wait_seconds, 2),
            )

        # Wait synchronously if allowed
        time.sleep(wait_seconds)
        self._refill()
        self.tokens = max(0.0, self.tokens - tokens)
        return True

    def get_metrics(self) -> dict[str, Any]:
        """Return current rate limiter state and counters."""
        self._refill()
        return {
            "provider": self.provider.value,
            "available_tokens": round(self.tokens, 2),
            "capacity": self.capacity,
            "refill_rate_per_sec": self.refill_rate,
            "total_throttled": self.total_throttled,
        }


class CircuitBreaker:
    """
    Three-state circuit breaker protecting downstream cloud providers.
    Prevents cascading resource exhaustion during outages.
    """

    def __init__(
        self,
        provider: CloudProvider,
        failure_threshold: int = 3,
        recovery_timeout: float = 5.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold

        self.state = CircuitBreakerState.CLOSED
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_state_change = time.monotonic()
        self.total_trips = 0

    def can_execute(self) -> bool:
        """Determine if a request can proceed based on circuit state."""
        now = time.monotonic()

        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has elapsed to enter HALF_OPEN
            if now - self.last_state_change >= self.recovery_timeout:
                logger.info(
                    "Circuit breaker for %s transitioning from OPEN to HALF_OPEN (probe mode)",
                    self.provider.value,
                )
                self.state = CircuitBreakerState.HALF_OPEN
                self.consecutive_successes = 0
                self.last_state_change = now
                return True
            return False

        if self.state == CircuitBreakerState.HALF_OPEN:
            return True

        return False

    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.half_open_success_threshold:
                logger.info(
                    "Circuit breaker for %s recovered! Transitioning from HALF_OPEN to CLOSED",
                    self.provider.value,
                )
                self.state = CircuitBreakerState.CLOSED
                self.consecutive_failures = 0
                self.consecutive_successes = 0
                self.last_state_change = time.monotonic()
        elif self.state == CircuitBreakerState.CLOSED:
            self.consecutive_failures = 0

    def record_failure(self, is_transient: bool = True) -> None:
        """Record a failed call. Only transient/system errors count against breaker."""
        if not is_transient:
            return

        now = time.monotonic()
        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.warning(
                "Circuit breaker for %s probe failed. Re-opening circuit for %.1fs",
                self.provider.value,
                self.recovery_timeout,
            )
            self.state = CircuitBreakerState.OPEN
            self.last_state_change = now
            self.total_trips += 1
        elif self.state == CircuitBreakerState.CLOSED:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.failure_threshold:
                logger.warning(
                    "Circuit breaker for %s tripped! (%d consecutive failures). Transitioning to OPEN for %.1fs",
                    self.provider.value,
                    self.consecutive_failures,
                    self.recovery_timeout,
                )
                self.state = CircuitBreakerState.OPEN
                self.last_state_change = now
                self.total_trips += 1

    def execute(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Wrap execution with circuit breaker protection."""
        if not self.can_execute():
            raise ProviderTransientError(
                provider=self.provider,
                message=(
                    f"Circuit breaker for {self.provider.value} is OPEN. "
                    f"Fast-failing request to protect downstream cloud provider."
                ),
            )

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except ProviderError as pe:
            self.record_failure(pe.retryable)
            raise
        except Exception as exc:
            self.record_failure(is_transient=True)
            raise

    def get_metrics(self) -> dict[str, Any]:
        """Return circuit breaker metrics."""
        return {
            "provider": self.provider.value,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "total_trips": self.total_trips,
            "recovery_timeout": self.recovery_timeout,
        }


class RetryPolicy:
    """Exponential backoff with full jitter retry mechanism."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.05,  # 50ms default base for snappy tests
        max_delay: float = 1.0,
        jitter: bool = True,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def compute_delay(self, attempt: int) -> float:
        """Compute delay for attempt using exponential backoff with jitter."""
        exponential = min(self.max_delay, self.base_delay * (2 ** attempt))
        if self.jitter:
            return random.uniform(exponential * 0.5, exponential * 1.5)
        return exponential

    def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        retryable_predicate: Optional[Callable[[Exception], bool]] = None,
        on_retry: Optional[Callable[[int, Exception, float], None]] = None,
        **kwargs: Any,
    ) -> T:
        """Execute callable with retries."""
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_error = exc

                # Check if error is retryable
                is_retryable = False
                if isinstance(exc, ProviderError):
                    is_retryable = exc.retryable
                elif retryable_predicate is not None:
                    is_retryable = retryable_predicate(exc)

                if not is_retryable or attempt >= self.max_retries:
                    raise

                delay = self.compute_delay(attempt)
                if on_retry:
                    on_retry(attempt, exc, delay)
                else:
                    logger.info(
                        "Retry attempt %d/%d after %.3fs due to error: %s",
                        attempt + 1,
                        self.max_retries,
                        delay,
                        exc,
                    )
                time.sleep(delay)

        if last_error:
            raise last_error
        raise RuntimeError("Retry policy reached unreachable terminal state")


class RequestTracer:
    """Request tracing and correlation ID generator."""

    @staticmethod
    def generate_trace_id(prefix: str = "cp") -> str:
        """Generate unique correlation trace ID."""
        return f"{prefix}-{secrets.token_hex(8)}"

    @staticmethod
    def generate_request_id(provider: CloudProvider) -> str:
        """Generate provider-scoped request ID."""
        return f"{provider.value}-req-{secrets.token_hex(6)}"
