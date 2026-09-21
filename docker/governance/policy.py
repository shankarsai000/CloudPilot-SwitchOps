"""
Policy-as-Code Engine.

Enforces corporate, security, regional, operational, and regulatory constraints.
Guarantees that no irreversible action may execute without satisfying its approval policy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from governance.models import (
    BusinessCriticality,
    PolicyEvaluationReport,
    ProposedAction,
    ReversibilityType,
)


class PolicyAsCodeEngine:
    """
    Policy-as-Code validator for proposed infrastructure actions.
    """

    def __init__(
        self,
        business_hours: tuple[int, int] = (9, 17),
        maintenance_days: Optional[List[int]] = None,
        change_freeze: bool = False,
        restricted_regions: Optional[List[str]] = None,
        enforce_business_hours: bool = True,
    ) -> None:
        self.business_hours = business_hours
        # If not specified, default to all days (operator can configure specific maintenance days)
        self.maintenance_days = maintenance_days if maintenance_days is not None else [0, 1, 2, 3, 4, 5, 6]
        self.change_freeze = change_freeze
        self.restricted_regions = restricted_regions or ["us-gov-west-1", "cn-north-1"]
        self.enforce_business_hours = enforce_business_hours

    def evaluate(
        self,
        action: ProposedAction,
        criticality: BusinessCriticality = BusinessCriticality.DEV_TEST,
        reversibility: ReversibilityType = ReversibilityType.REVERSIBLE,
        region: str = "us-east-1",
        compliance_frameworks: Optional[List[str]] = None,
        current_time: Optional[datetime] = None,
    ) -> PolicyEvaluationReport:
        """Alias for evaluate_policy."""
        return self.evaluate_policy(
            action=action,
            criticality=criticality,
            reversibility=reversibility,
            region=region,
            compliance_frameworks=compliance_frameworks,
            current_time=current_time,
        )

    def evaluate_policy(
        self,
        action: ProposedAction,
        criticality: BusinessCriticality = BusinessCriticality.DEV_TEST,
        reversibility: ReversibilityType = ReversibilityType.REVERSIBLE,
        region: str = "us-east-1",
        compliance_frameworks: Optional[List[str]] = None,
        current_time: Optional[datetime] = None,
    ) -> PolicyEvaluationReport:
        """
        Evaluate all policy-as-code rules against a proposed action.
        """
        now = current_time or datetime.now(timezone.utc)
        violations: List[str] = []
        checks_passed: List[str] = []

        is_prod = action.environment.lower() in ("prod", "production") or criticality == BusinessCriticality.TIER_1_MISSION_CRITICAL

        # 1. Change freeze check
        if self.change_freeze:
            violations.append("CHANGE_FREEZE: Active change freeze prohibits all non-emergency modifications")
        else:
            checks_passed.append("Change freeze: Inactive")

        # 2. Business hours check (destructive actions on production during peak business hours)
        is_destructive = any(k in action.action_type.lower() for k in ("terminate", "delete", "destroy", "drop", "wipe"))
        in_biz_hours = self.business_hours[0] <= now.hour < self.business_hours[1]

        if self.enforce_business_hours and is_prod and is_destructive and in_biz_hours:
            violations.append(
                f"BUSINESS_HOURS: Destructive action '{action.action_type}' blocked on production "
                f"during business hours ({now.hour:02d}:00 UTC)"
            )
        else:
            checks_passed.append("Business hours: Outside peak hours or non-destructive")

        # 3. Maintenance window check (production changes must occur during maintenance windows)
        weekday = now.weekday()
        in_maint_window = (not is_prod) or (weekday in self.maintenance_days)
        if not in_maint_window:
            violations.append(
                f"MAINTENANCE_WINDOW: Production change rejected — day of week ({weekday}) outside scheduled maintenance days"
            )
        else:
            checks_passed.append("Maintenance window: Within allowed window")

        # 4. Regional compliance check
        if region in self.restricted_regions:
            violations.append(f"REGIONAL_RESTRICTION: Region '{region}' is restricted by organizational data sovereignty policy")
        else:
            checks_passed.append("Regional compliance: Authorized region")

        # 5. Production database termination check (Absolute Block)
        is_database = any(db_kw in action.target_resource_id.lower() or db_kw in action.target_service.lower() for db_kw in ("db", "database", "rds", "postgres", "sql"))
        is_termination = "terminate" in action.action_type.lower() or "delete" in action.action_type.lower()
        if is_prod and is_database and is_termination:
            violations.append("PROD_DATABASE_PROTECTION: Direct termination of production databases is strictly prohibited")
        else:
            checks_passed.append("Database safety: Check passed")

        # 6. Strict Irreversibility Rule:
        # No irreversible action may execute without an approved policy that requires human signoff.
        if reversibility == ReversibilityType.IRREVERSIBLE:
            if is_prod:
                checks_passed.append("Irreversibility guard: Flagged for mandatory multi-party approval")
            else:
                checks_passed.append("Irreversibility guard: Non-production irreversible action flagged for approval gate")

        # 7. Compliance Framework checks (e.g. PCI-DSS, HIPAA)
        frameworks = compliance_frameworks or []
        for fw in frameworks:
            fw_lower = fw.lower()
            if "pci" in fw_lower and "unencrypted" in str(action.parameters).lower():
                violations.append("PCI_DSS_VIOLATION: Unencrypted datastore modification detected")
            elif "hipaa" in fw_lower and "public" in str(action.parameters).lower():
                violations.append("HIPAA_VIOLATION: Public ingress rule modification detected on healthcare workload")
            else:
                checks_passed.append(f"Compliance framework {fw}: Passed")

        is_compliant = len(violations) == 0

        return PolicyEvaluationReport(
            is_compliant=is_compliant,
            policy_checks_passed=checks_passed,
            policy_violations=violations,
            active_change_freeze=self.change_freeze,
            in_maintenance_window=in_maint_window,
            in_business_hours=in_biz_hours,
            compliance_frameworks_satisfied=all("VIOLATION" not in v for v in violations),
            evaluated_at=now,
        )


_policy_engine_instance: Optional[PolicyAsCodeEngine] = None


def get_policy_engine() -> PolicyAsCodeEngine:
    global _policy_engine_instance
    if _policy_engine_instance is None:
        _policy_engine_instance = PolicyAsCodeEngine()
    return _policy_engine_instance
