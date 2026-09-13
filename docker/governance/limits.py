"""
Rate Limiting, Execution Budgets, & Blast Radius Limits.

Enforces:
- Action execution throughput ceilings (RateLimiter)
- Financial and resource change budget ceilings (ExecutionBudgetTracker)
- Maximum allowable blast radius thresholds (BlastRadiusGovernor)
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import threading
from typing import Deque, Dict, Optional, Tuple


class RateLimiter:
    """
    Sliding-window rate limiter enforcing operation ceilings per environment.
    """

    def __init__(
        self,
        prod_limit_per_hour: int = 5,
        nonprod_limit_per_hour: int = 30,
    ) -> None:
        self._limits: Dict[str, int] = {
            "prod": prod_limit_per_hour,
            "production": prod_limit_per_hour,
            "staging": nonprod_limit_per_hour,
            "dev": nonprod_limit_per_hour,
            "default": nonprod_limit_per_hour,
        }
        # Deque of timestamps per environment
        self._history: Dict[str, Deque[datetime]] = {}
        self._mutex = threading.Lock()

    def check_rate_limit(self, environment: str = "dev") -> Tuple[bool, str]:
        """
        Check if an action can be executed under the current rate limit.
        Returns (is_allowed, message).
        """
        env_key = environment.strip().lower()
        limit = self._limits.get(env_key, self._limits["default"])
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        with self._mutex:
            queue = self._history.setdefault(env_key, deque())
            # Purge entries older than 1 hour
            while queue and queue[0] < one_hour_ago:
                queue.popleft()

            if len(queue) >= limit:
                return (
                    False,
                    f"RATE_LIMIT_EXCEEDED: Environment '{environment}' exceeded limit of {limit} actions/hour (currently {len(queue)})",
                )
            return True, "Rate limit check passed"

    def record_action(self, environment: str = "dev") -> None:
        """Record an executed action timestamp for rate limiting."""
        env_key = environment.strip().lower()
        now = datetime.now(timezone.utc)
        with self._mutex:
            queue = self._history.setdefault(env_key, deque())
            queue.append(now)

    def reset_all(self) -> None:
        with self._mutex:
            self._history.clear()


class ExecutionBudgetTracker:
    """
    Tracks and caps cumulative financial modifications and resource destructions
    within a rolling 24-hour window.
    """

    def __init__(
        self,
        max_daily_budget_usd: float = 10000.0,
        max_destructions_per_batch: int = 5,
    ) -> None:
        self.max_daily_budget_usd = max_daily_budget_usd
        self.max_destructions_per_batch = max_destructions_per_batch
        # List of (timestamp, cost_impact_usd, destroyed_count)
        self._entries: Deque[Tuple[datetime, float, int]] = deque()
        self._mutex = threading.Lock()

    def check_budget(
        self,
        cost_impact_usd: float,
        destruction_count: int = 0,
    ) -> Tuple[bool, str]:
        """
        Verify that a proposed action does not exceed daily budget or batch destruction limits.
        """
        if destruction_count > self.max_destructions_per_batch:
            return (
                False,
                f"BUDGET_EXCEEDED: Destructions count ({destruction_count}) exceeds batch maximum ({self.max_destructions_per_batch})",
            )

        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(hours=24)

        with self._mutex:
            # Purge older than 24h
            while self._entries and self._entries[0][0] < one_day_ago:
                self._entries.popleft()

            current_spent = sum(abs(item[1]) for item in self._entries)
            proposed_total = current_spent + abs(cost_impact_usd)

            if proposed_total > self.max_daily_budget_usd:
                return (
                    False,
                    f"BUDGET_EXCEEDED: Daily change budget of ${self.max_daily_budget_usd:,.2f} exceeded (projected: ${proposed_total:,.2f})",
                )
            return True, "Execution budget check passed"

    def record_spend(self, cost_impact_usd: float, destruction_count: int = 0) -> None:
        now = datetime.now(timezone.utc)
        with self._mutex:
            self._entries.append((now, cost_impact_usd, destruction_count))

    def reset_all(self) -> None:
        with self._mutex:
            self._entries.clear()


class BlastRadiusGovernor:
    """
    Hard limits on allowable blast radius for autonomous actions.
    """

    def __init__(
        self,
        max_autonomous_blast_score: float = 0.35,
        max_autonomous_affected_services: int = 2,
    ) -> None:
        self.max_autonomous_blast_score = max_autonomous_blast_score
        self.max_autonomous_affected_services = max_autonomous_affected_services

    def check_blast_radius(
        self,
        dependent_services_count: int,
        blast_radius_score: float,
        is_autonomous: bool = True,
    ) -> Tuple[bool, str]:
        """
        Check if blast radius is within acceptable thresholds.
        Autonomous operations (L4/L5) have stricter bounds than human-approved operations (L3).
        """
        if is_autonomous:
            if dependent_services_count > self.max_autonomous_affected_services:
                return (
                    False,
                    f"BLAST_RADIUS_EXCEEDED: Action affects {dependent_services_count} services "
                    f"(autonomous ceiling is {self.max_autonomous_affected_services})",
                )
            if blast_radius_score > self.max_autonomous_blast_score:
                return (
                    False,
                    f"BLAST_RADIUS_EXCEEDED: Blast score {blast_radius_score:.2f} exceeds "
                    f"autonomous ceiling of {self.max_autonomous_blast_score:.2f}",
                )
        return True, "Blast radius check passed"


_rate_limiter_instance: Optional[RateLimiter] = None
_budget_tracker_instance: Optional[ExecutionBudgetTracker] = None
_blast_governor_instance: Optional[BlastRadiusGovernor] = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter()
    return _rate_limiter_instance


def get_budget_tracker() -> ExecutionBudgetTracker:
    global _budget_tracker_instance
    if _budget_tracker_instance is None:
        _budget_tracker_instance = ExecutionBudgetTracker()
    return _budget_tracker_instance


def get_blast_radius_governor() -> BlastRadiusGovernor:
    global _blast_governor_instance
    if _blast_governor_instance is None:
        _blast_governor_instance = BlastRadiusGovernor()
    return _blast_governor_instance
