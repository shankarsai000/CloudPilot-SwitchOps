"""
CloudPilot SwitchOps — SecOps and SRE Intelligence Engine

Runs deterministic, evidence-backed security vulnerability inspections
and reliability/resilience audits across discovered infrastructure resources.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from app.domain.finding import Finding, FindingCategory, FindingSeverity
from app.domain.inventory import InfrastructureInventory
from app.services.secops import rules

logger = logging.getLogger("cloudpilot.secops.engine")


class SecOpsAnalysisResult(BaseModel):
    """Consolidated findings and summary metrics from security and reliability analysis."""
    task_id: Optional[str] = None
    workspace_root: str
    security_findings: List[Finding] = Field(default_factory=list)
    reliability_findings: List[Finding] = Field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    security_summary: str = ""
    reliability_summary: str = ""

    @property
    def total_findings(self) -> int:
        return len(self.security_findings) + len(self.reliability_findings)

    @property
    def all_findings(self) -> List[Finding]:
        return self.security_findings + self.reliability_findings


class SecOpsEngine:
    """
    Deterministic rule evaluator for infrastructure security posture and SRE reliability.
    """

    def analyze(
        self,
        inventory: InfrastructureInventory,
        task_id: str = "task-local",
    ) -> SecOpsAnalysisResult:
        """
        Executes all active SEC-* and REL-* rules across the discovered infrastructure resources.
        """
        sec_findings: List[Finding] = []
        rel_findings: List[Finding] = []

        all_res = inventory.resources

        for res in all_res:
            # --- Security Rules ---
            # SEC-001: Redis exposure
            f_sec1 = rules.evaluate_sec_001_redis_exposure(res, task_id)
            if f_sec1:
                sec_findings.append(f_sec1)

            # SEC-002: DB port exposure
            f_sec2 = rules.evaluate_sec_002_database_exposure(res, task_id)
            if f_sec2:
                sec_findings.append(f_sec2)

            # SEC-003: Security group unrestricted ingress
            f_sec3_list = rules.evaluate_sec_003_unrestricted_ingress(res, task_id)
            sec_findings.extend(f_sec3_list)

            # SEC-004: Privileged container
            f_sec4 = rules.evaluate_sec_004_privileged_container(res, task_id)
            if f_sec4:
                sec_findings.append(f_sec4)

            # SEC-005: Docker socket mount
            f_sec5 = rules.evaluate_sec_005_docker_socket_mount(res, task_id)
            if f_sec5:
                sec_findings.append(f_sec5)

            # SEC-006: Host network mode
            f_sec6 = rules.evaluate_sec_006_host_network_mode(res, task_id)
            if f_sec6:
                sec_findings.append(f_sec6)

            # SEC-007: S3 public access block
            f_sec7 = rules.evaluate_sec_007_s3_public_access(res, all_res, task_id)
            if f_sec7:
                sec_findings.append(f_sec7)

            # SEC-008: Unencrypted EBS
            f_sec8 = rules.evaluate_sec_008_unencrypted_ebs(res, task_id)
            if f_sec8:
                sec_findings.append(f_sec8)

            # SEC-009: Unencrypted RDS
            f_sec9 = rules.evaluate_sec_009_unencrypted_rds(res, task_id)
            if f_sec9:
                sec_findings.append(f_sec9)

            # SEC-010: Plaintext credentials
            f_sec10_list = rules.evaluate_sec_010_plaintext_credentials(res, task_id)
            sec_findings.extend(f_sec10_list)

            # --- Reliability Rules ---
            # REL-001: Missing healthcheck
            f_rel1 = rules.evaluate_rel_001_missing_healthcheck(res, task_id)
            if f_rel1:
                rel_findings.append(f_rel1)

            # REL-002: Missing restart policy
            f_rel2 = rules.evaluate_rel_002_missing_restart_policy(res, task_id)
            if f_rel2:
                rel_findings.append(f_rel2)

            # REL-003: Single point of failure (SPOF)
            f_rel3 = rules.evaluate_rel_003_single_point_of_failure(res, task_id)
            if f_rel3:
                rel_findings.append(f_rel3)

            # REL-004: Missing resource limits
            f_rel4 = rules.evaluate_rel_004_missing_resource_limits(res, task_id)
            if f_rel4:
                rel_findings.append(f_rel4)

            # REL-005: Stateful DB missing volume
            f_rel5 = rules.evaluate_rel_005_stateful_database_missing_volume(res, task_id)
            if f_rel5:
                rel_findings.append(f_rel5)

        # Count severities
        all_f = sec_findings + rel_findings
        crit = sum(1 for f in all_f if f.severity == FindingSeverity.CRITICAL)
        high = sum(1 for f in all_f if f.severity == FindingSeverity.HIGH)
        med = sum(1 for f in all_f if f.severity == FindingSeverity.MEDIUM)
        low = sum(1 for f in all_f if f.severity == FindingSeverity.LOW)

        sec_summary = (
            f"SecOps audit identified {len(sec_findings)} security issue(s) "
            f"({crit} critical, {high} high, {med} medium, {low} low across security posture)."
        )

        rel_summary = (
            f"Reliability analysis identified {len(rel_findings)} resilience deficit(s) "
            f"affecting operational stability and container availability."
        )

        return SecOpsAnalysisResult(
            task_id=task_id,
            workspace_root=inventory.workspace_root,
            security_findings=sec_findings,
            reliability_findings=rel_findings,
            critical_count=crit,
            high_count=high,
            medium_count=med,
            low_count=low,
            security_summary=sec_summary,
            reliability_summary=rel_summary,
        )
