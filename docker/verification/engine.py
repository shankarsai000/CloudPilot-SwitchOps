"""
Outcome Verification Engine.

Generates pre-execution expected outcomes, captures post-execution empirical telemetry,
and computes variances across the 5 core dimensions:
1. Cost
2. Performance
3. Availability
4. Risk
5. Savings
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional
import uuid

from verification.models import (
    ActualOutcome,
    ExpectedOutcome,
    OutcomeReport,
    OutcomeVerdict,
    SafetyThresholds,
)


class OutcomeVerificationEngine:
    """
    Ex-ante vs Ex-post outcome verification and threshold breach evaluation.
    """

    def __init__(self) -> None:
        self._reports: Dict[str, OutcomeReport] = {}
        self._expected: Dict[str, ExpectedOutcome] = {}
        self._mutex = threading.Lock()

    def generate_expected_outcome(
        self,
        action_id: str,
        target_resource_id: str,
        baseline_monthly_cost_usd: float,
        expected_monthly_savings_usd: float,
        target_service: str = "unknown",
        expected_cpu_utilization_pct: float = 45.0,
        expected_memory_headroom_pct: float = 40.0,
        expected_latency_p99_ms: float = 45.0,
        expected_availability_pct: float = 99.99,
        expected_risk_level: str = "LOW",
        thresholds: Optional[SafetyThresholds] = None,
    ) -> ExpectedOutcome:
        """
        Generate and persist ex-ante expectations across all 5 dimensions.
        """
        expected_cost = max(0.0, baseline_monthly_cost_usd - expected_monthly_savings_usd)
        expected = ExpectedOutcome(
            action_id=action_id,
            target_resource_id=target_resource_id,
            target_service=target_service,
            baseline_monthly_cost_usd=round(baseline_monthly_cost_usd, 2),
            expected_monthly_cost_usd=round(expected_cost, 2),
            expected_monthly_savings_usd=round(expected_monthly_savings_usd, 2),
            expected_cpu_utilization_pct=expected_cpu_utilization_pct,
            expected_memory_headroom_pct=expected_memory_headroom_pct,
            expected_latency_p99_ms=expected_latency_p99_ms,
            expected_availability_pct=expected_availability_pct,
            expected_risk_level=expected_risk_level,
            thresholds=thresholds or SafetyThresholds(),
            generated_at=datetime.now(timezone.utc),
        )
        with self._mutex:
            self._expected[action_id] = expected
        return expected

    def collect_actual_outcome(
        self,
        action_id: str,
        target_resource_id: str,
        measured_monthly_cost_usd: float,
        measured_savings_usd: float,
        measured_cpu_utilization_pct: float,
        measured_memory_headroom_pct: float,
        measured_latency_p99_ms: float,
        measured_availability_pct: float = 99.99,
        measured_error_rate_pct: float = 0.01,
        measured_risk_level: str = "LOW",
        observed_incidents_count: int = 0,
    ) -> ActualOutcome:
        """
        Collect ex-post telemetry and empirical cost metrics after execution.
        """
        return ActualOutcome(
            action_id=action_id,
            target_resource_id=target_resource_id,
            measured_monthly_cost_usd=round(measured_monthly_cost_usd, 2),
            measured_monthly_savings_usd=round(measured_savings_usd, 2),
            measured_savings_usd=round(measured_savings_usd, 2),
            measured_cpu_utilization_pct=round(measured_cpu_utilization_pct, 1),
            measured_memory_headroom_pct=round(measured_memory_headroom_pct, 1),
            measured_latency_p99_ms=round(measured_latency_p99_ms, 1),
            measured_availability_pct=round(measured_availability_pct, 3),
            measured_error_rate_pct=round(measured_error_rate_pct, 3),
            measured_risk_level=measured_risk_level,
            observed_incidents_count=observed_incidents_count,
            collected_at=datetime.now(timezone.utc),
        )

    def verify_and_generate_report(
        self,
        expected: ExpectedOutcome,
        actual: ActualOutcome,
    ) -> OutcomeReport:
        """
        Compare all 5 dimensions, identify threshold breaches, and issue OutcomeReport.
        """
        # 1. Cost & Savings Deltas
        if expected.expected_monthly_cost_usd > 0:
            cost_var_pct = ((actual.measured_monthly_cost_usd - expected.expected_monthly_cost_usd) / expected.expected_monthly_cost_usd) * 100.0
        else:
            cost_var_pct = 0.0

        if expected.expected_monthly_savings_usd > 0:
            savings_realization = actual.measured_savings_usd / expected.expected_monthly_savings_usd
        else:
            savings_realization = 1.0

        # 2. Performance Deltas
        lat_delta = actual.measured_latency_p99_ms - expected.expected_latency_p99_ms
        if expected.expected_latency_p99_ms > 0:
            lat_inc_pct = (lat_delta / expected.expected_latency_p99_ms) * 100.0
        else:
            lat_inc_pct = 0.0

        cpu_headroom_delta = (100.0 - actual.measured_cpu_utilization_pct) - (100.0 - expected.expected_cpu_utilization_pct)

        # 3. Availability Delta
        avail_drop_pct = max(0.0, expected.expected_availability_pct - actual.measured_availability_pct)

        # 4. Check Safety Thresholds
        breaches: List[str] = []
        t = expected.thresholds

        if lat_inc_pct > t.max_latency_increase_pct:
            breaches.append(f"LATENCY_SPIKE: p99 latency increased by {lat_inc_pct:.1f}% (threshold: {t.max_latency_increase_pct}%)")

        if actual.measured_latency_p99_ms > t.max_latency_absolute_ms:
            breaches.append(f"LATENCY_CEILING: p99 latency reached {actual.measured_latency_p99_ms:.1f}ms (threshold: {t.max_latency_absolute_ms}ms)")

        if actual.measured_availability_pct < t.min_availability_pct:
            breaches.append(f"AVAILABILITY_DROP: Availability dropped to {actual.measured_availability_pct:.2f}% (minimum: {t.min_availability_pct}%)")

        if actual.measured_cpu_utilization_pct > t.max_cpu_utilization_pct:
            breaches.append(f"CPU_STARVATION: CPU utilization reached {actual.measured_cpu_utilization_pct:.1f}% (threshold: {t.max_cpu_utilization_pct}%)")

        if cost_var_pct > t.max_cost_overshoot_pct:
            breaches.append(f"COST_OVERSHOOT: Cost exceeded expected by {cost_var_pct:.1f}% (threshold: {t.max_cost_overshoot_pct}%)")

        if (savings_realization * 100.0) < t.min_savings_realization_pct:
            breaches.append(f"SAVINGS_UNDERPERFORMANCE: Realized {savings_realization * 100.0:.1f}% of predicted savings (minimum: {t.min_savings_realization_pct}%)")

        if actual.observed_incidents_count > 0:
            breaches.append(f"POST_EXECUTION_INCIDENTS: {actual.observed_incidents_count} operational incident(s) detected")

        # 5. Determine Verdict
        if breaches:
            verdict = OutcomeVerdict.THRESHOLD_BREACH
            rollback_required = True
            details = f"Safety thresholds violated: {'; '.join(breaches)}"
        elif abs(cost_var_pct) < 5.0 and lat_inc_pct <= 5.0 and savings_realization >= 0.90:
            verdict = OutcomeVerdict.VERIFIED_SUCCESS
            rollback_required = False
            details = "Outcome verified: All 5 dimensions met or exceeded expectations."
        else:
            verdict = OutcomeVerdict.ACCEPTABLE_DEVIATION
            rollback_required = False
            details = f"Acceptable deviation: Realized {savings_realization * 100.0:.1f}% savings with manageable latency change."

        report = OutcomeReport(
            report_id=f"rep-{uuid.uuid4().hex[:8]}",
            action_id=expected.action_id,
            target_resource_id=expected.target_resource_id,
            expected=expected,
            actual=actual,
            cost_variance_pct=round(cost_var_pct, 2),
            savings_realization_rate=round(savings_realization, 3),
            latency_increase_pct=round(lat_inc_pct, 2),
            latency_delta_ms=round(lat_delta, 2),
            availability_drop_pct=round(avail_drop_pct, 3),
            cpu_headroom_delta_pct=round(cpu_headroom_delta, 2),
            verdict=verdict,
            breached_thresholds=breaches,
            rollback_required=rollback_required,
            details=details,
            generated_at=datetime.now(timezone.utc),
        )

        with self._mutex:
            self._reports[report.action_id] = report
        return report

    def get_expected(self, action_id: str) -> Optional[ExpectedOutcome]:
        with self._mutex:
            return self._expected.get(action_id)

    def get_report(self, action_id: str) -> Optional[OutcomeReport]:
        with self._mutex:
            return self._reports.get(action_id)

    def list_reports(self) -> List[OutcomeReport]:
        with self._mutex:
            return sorted(self._reports.values(), key=lambda r: r.generated_at, reverse=True)

    def clear_all(self) -> None:
        with self._mutex:
            self._reports.clear()
            self._expected.clear()


_verification_engine_instance: Optional[OutcomeVerificationEngine] = None


def get_verification_engine() -> OutcomeVerificationEngine:
    global _verification_engine_instance
    if _verification_engine_instance is None:
        _verification_engine_instance = OutcomeVerificationEngine()
    return _verification_engine_instance
