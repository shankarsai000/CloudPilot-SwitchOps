"""
CloudPilot SwitchOps — Unit Tests: SecOps & SRE Reliability Engine

Tests deterministic rule execution for SEC-001 through SEC-010,
REL-001 through REL-005, and posture verification on staging and safe scenarios.
"""

import pytest

from app.domain.finding import FindingCategory, FindingSeverity
from app.services.discovery.engine import InfrastructureDiscoveryEngine
from app.services.secops.engine import SecOpsEngine


class TestSecOpsEngine:
    """Verifies security vulnerability detection and SRE reliability audits."""

    def test_secops_analysis_on_staging_flags_critical_issues(self) -> None:
        discovery = InfrastructureDiscoveryEngine()
        inventory = discovery.discover_workspace("samples/staging", task_id="secops-test-task")

        secops = SecOpsEngine()
        result = secops.analyze(inventory=inventory, task_id="secops-test-task")

        assert result.task_id == "secops-test-task"
        assert result.critical_count >= 2
        assert result.high_count >= 3

        sec_rule_ids = {f.rule_id for f in result.security_findings}
        rel_rule_ids = {f.rule_id for f in result.reliability_findings}

        # Verify key security rules fired
        assert "SEC-001" in sec_rule_ids  # Redis public binding
        assert "SEC-002" in sec_rule_ids  # DB port exposed
        assert "SEC-003" in sec_rule_ids  # 0.0.0.0/0 ingress
        assert "SEC-004" in sec_rule_ids  # Privileged container
        assert "SEC-005" in sec_rule_ids  # Docker socket mount
        assert "SEC-006" in sec_rule_ids  # Host network mode
        assert "SEC-007" in sec_rule_ids  # S3 public ACL
        assert "SEC-008" in sec_rule_ids  # Unencrypted EBS
        assert "SEC-009" in sec_rule_ids  # Unencrypted RDS
        assert "SEC-010" in sec_rule_ids  # Plaintext password

        # Verify key reliability rules fired
        assert "REL-001" in rel_rule_ids  # Missing healthcheck
        assert "REL-002" in rel_rule_ids  # Suboptimal restart policy
        assert "REL-003" in rel_rule_ids  # Single-AZ RDS
        assert "REL-004" in rel_rule_ids  # Missing resource limits
        assert "REL-005" in rel_rule_ids  # Stateful DB missing volume

    def test_safe_scenario_produces_zero_critical_security_findings(self) -> None:
        discovery = InfrastructureDiscoveryEngine()
        inventory = discovery.discover_workspace("samples/safe", task_id="safe-test-task")

        secops = SecOpsEngine()
        result = secops.analyze(inventory=inventory, task_id="safe-test-task")

        # Zero critical or high security issues in hardened environment
        critical_high_sec = [
            f for f in result.security_findings
            if f.severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH)
        ]
        assert len(critical_high_sec) == 0

        # Safe compose has healthchecks and persistent volumes
        rel_rules = {f.rule_id for f in result.reliability_findings}
        assert "REL-005" not in rel_rules  # Volumes are configured
