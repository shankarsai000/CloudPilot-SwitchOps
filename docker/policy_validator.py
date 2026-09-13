"""
Policy Validator Component

Enforces organizational policies: security, compliance, business hours,
maintenance windows, regional policies, and change freeze.
Never bypasses policies.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from models_decision import PolicyComplianceReport

logger = logging.getLogger(__name__)


class PolicyValidator:
    """Validates decisions against organizational policies."""

    def __init__(
        self,
        business_hours: tuple[int, int] = (9, 17),
        maintenance_days: list[int] = None,
        change_freeze: bool = False,
        restricted_regions: list[str] = None,
    ) -> None:
        """Initialize Policy Validator.

        Args:
            business_hours: Tuple of (start_hour, end_hour) in 24h format
            maintenance_days: Allowed maintenance weekdays (0=Mon, 6=Sun)
            change_freeze: Whether a change freeze is active
            restricted_regions: Regions where changes are restricted
        """
        self.business_hours = business_hours
        self.maintenance_days = maintenance_days or [0, 1, 2, 3, 4]  # weekdays
        self.change_freeze = change_freeze
        self.restricted_regions = restricted_regions or []

    def validate(
        self,
        target_id: str,
        action: str,
        region: str = "us-east-1",
        is_production: bool = False,
        compliance_frameworks: list[str] = None,
        current_time: datetime = None,
    ) -> PolicyComplianceReport:
        """Run all policy checks against a proposed action.

        Args:
            target_id: Resource or application ID
            action: Proposed action
            region: Target region
            is_production: Whether the target is production
            compliance_frameworks: Active compliance frameworks (e.g. pci-dss, hipaa)
            current_time: Current time (for testability)

        Returns:
            PolicyComplianceReport with all check results
        """
        now = current_time or datetime.utcnow()
        violations: list[str] = []
        checks_passed: list[str] = []
        frameworks = compliance_frameworks or []

        # 1. Change freeze check
        if self.change_freeze:
            violations.append("CHANGE_FREEZE: Organization-wide change freeze is active.")
        else:
            checks_passed.append("Change freeze: not active")

        # 2. Business hours check for production
        if is_production and action in ("TERMINATE", "DELETE", "RESIZE"):
            hour = now.hour
            if self.business_hours[0] <= hour < self.business_hours[1]:
                violations.append(
                    f"BUSINESS_HOURS: Destructive action '{action}' on production resource during business hours ({hour}:00)."
                )
            else:
                checks_passed.append("Business hours: outside peak hours")
        else:
            checks_passed.append("Business hours: non-production or safe action")

        # 3. Maintenance window check (enforced for production)
        weekday = now.weekday()
        if is_production and weekday not in self.maintenance_days:
            violations.append(
                f"MAINTENANCE_WINDOW: Today ({weekday}) is not within allowed maintenance days."
            )
        else:
            checks_passed.append("Maintenance window: within allowed days or non-production")

        # 4. Regional policy check
        if region in self.restricted_regions:
            violations.append(f"REGIONAL_POLICY: Region '{region}' is restricted for changes.")
        else:
            checks_passed.append(f"Regional policy: '{region}' is allowed")

        # 5. Compliance framework checks
        if "pci-dss" in frameworks and action in ("TERMINATE", "DELETE"):
            violations.append("COMPLIANCE_PCI: PCI-DSS environments cannot have destructive actions without audit sign-off.")
        elif "pci-dss" in frameworks:
            checks_passed.append("Compliance PCI: non-destructive action")

        if "hipaa" in frameworks and action in ("TERMINATE", "DELETE"):
            violations.append("COMPLIANCE_HIPAA: HIPAA environments require additional approval for destructive actions.")
        elif "hipaa" in frameworks:
            checks_passed.append("Compliance HIPAA: non-destructive action")

        if not frameworks:
            checks_passed.append("Compliance: no special frameworks")

        # 6. Security check for terminate/delete on production
        if is_production and action in ("TERMINATE", "DELETE"):
            violations.append(f"SECURITY: Destructive action '{action}' on production resource requires SRE override.")
        elif is_production:
            checks_passed.append("Security: non-destructive production action")
        else:
            checks_passed.append("Security: non-production target")

        is_compliant = len(violations) == 0

        return PolicyComplianceReport(
            is_compliant=is_compliant,
            violations=violations,
            checks_passed=checks_passed,
            change_freeze_active=self.change_freeze,
            maintenance_window_ok=weekday in self.maintenance_days,
        )
