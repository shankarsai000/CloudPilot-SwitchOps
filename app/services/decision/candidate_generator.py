"""
CloudPilot SwitchOps — Deterministic Candidate Generation Engine

Generates actionable, evidence-backed candidate change proposals from
Phase 2 infrastructure discovery inventories and specialist assessment findings.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Dict, List, Optional

from app.domain.candidates import (
    ApplicabilityStatus,
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
    ProposedChange,
)
from app.domain.finding import Finding
from app.domain.inventory import DiscoveredResource, InfrastructureInventory
from app.domain.policies import PolicyConfiguration
from app.services.finops.catalog import PricingCatalog

logger = logging.getLogger("cloudpilot.decision.candidates")
TWO_PLACES = Decimal("0.01")


class CandidateGenerator:
    """
    Deterministic candidate generation engine.
    Transforms assessment findings and discovered resource declarations into typed change candidates.
    Guarantees idempotence: identical assessment inputs produce identical candidate sets.
    """

    def __init__(self, catalog: Optional[PricingCatalog] = None) -> None:
        self.catalog = catalog or PricingCatalog()
        self.monthly_hours = Decimal(str(self.catalog.standard_monthly_hours))

    def generate_candidates(
        self,
        inventory: InfrastructureInventory,
        findings: List[Finding],
        policy_config: Optional[PolicyConfiguration] = None,
        include_adversarial_test_candidates: bool = True,
    ) -> List[Candidate]:
        """
        Generate candidate change proposals from discovered inventory and assessment findings.
        """
        candidates: List[Candidate] = []
        resources_by_name = {r.name: r for r in inventory.resources}
        resources_by_id = {r.resource_id: r for r in inventory.resources}

        # Index findings by rule_id
        findings_by_rule: Dict[str, List[Finding]] = {}
        for f in findings:
            findings_by_rule.setdefault(f.rule_id, []).append(f)

        # 1. FIN-001: Resize Oversized Compute Instance
        for f in findings_by_rule.get("FIN-001", []):
            res = self._find_resource_for_finding(f, inventory)
            if res and res.resource_type == "aws_instance":
                cand = self._create_ec2_resize_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 2. FIN-005: Downgrade Provisioned IOPS Storage to GP3
        for f in findings_by_rule.get("FIN-005", []):
            res = self._find_resource_for_finding(f, inventory)
            if res and res.resource_type == "aws_ebs_volume":
                cand = self._create_ebs_downgrade_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 3. FIN-003: Apply Off-Hours Schedule to Staging Database
        for f in findings_by_rule.get("FIN-003", []):
            res = self._find_resource_for_finding(f, inventory)
            if res and res.resource_type in ("aws_db_instance", "aws_rds_cluster_instance"):
                cand = self._create_db_schedule_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 4. FIN-002: Add Resource Limits to Containers
        for f in findings_by_rule.get("FIN-002", []):
            res = self._find_resource_for_finding(f, inventory)
            if res and res.resource_type == "compose_service":
                cand = self._create_container_limits_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 5. SEC-001: Isolate Redis Cache to Localhost
        for f in findings_by_rule.get("SEC-001", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_isolate_redis_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 6. SEC-002: Isolate Exposed Database Container
        for f in findings_by_rule.get("SEC-002", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_isolate_db_port_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 7. SEC-003: Restrict Unrestricted Security Group Ingress
        for f in findings_by_rule.get("SEC-003", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_restrict_ingress_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 8. SEC-004: Remove Privileged Container Execution
        for f in findings_by_rule.get("SEC-004", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_remove_privileged_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 9. SEC-005: Remove Host Docker Socket Mount
        for f in findings_by_rule.get("SEC-005", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_remove_socket_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 10. SEC-007: Secure S3 Bucket Public Access Block
        for f in findings_by_rule.get("SEC-007", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_s3_secure_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 11. SEC-008 & SEC-009: Enable Encryption at Rest
        for f in findings_by_rule.get("SEC-008", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_enable_encryption_candidate(res, f, "EBS Volume")
                if cand:
                    candidates.append(cand)

        for f in findings_by_rule.get("SEC-009", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_enable_encryption_candidate(res, f, "RDS Database")
                if cand:
                    candidates.append(cand)

        # 12. REL-001: Add Container Healthcheck
        for f in findings_by_rule.get("REL-001", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_add_healthcheck_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 13. REL-002: Set Container Restart Policy
        for f in findings_by_rule.get("REL-002", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_set_restart_policy_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 14. REL-003: Multi-AZ High Availability Upgrade
        for f in findings_by_rule.get("REL-003", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_multiaz_upgrade_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 15. REL-005: Add Persistent Volume to Stateful DB Container
        for f in findings_by_rule.get("REL-005", []):
            res = self._find_resource_for_finding(f, inventory)
            if res:
                cand = self._create_add_volume_candidate(res, f)
                if cand:
                    candidates.append(cand)

        # 16. Deliberate Adversarial/Flawed Candidates for Hard Constraint Testing
        if include_adversarial_test_candidates:
            # Flawed candidate 1: Remove persistent volume to save fake storage cost (violates CONST-REL-01)
            db_res = next((r for r in inventory.resources if "postgres" in r.name.lower() or "db" in r.name.lower()), None)
            if db_res:
                candidates.append(
                    Candidate(
                        candidate_id=f"cand-unsafe-drop-persistence-{db_res.name}",
                        title=f"Drop persistent volume on {db_res.name} to minimize storage costs",
                        description="Dangerous cost-cutting measure that switches database container to ephemeral storage, risking total data loss.",
                        candidate_type=CandidateType.DROP_PERSISTENCE,
                        affected_resource_ids=[db_res.resource_id],
                        proposed_changes=[
                            ProposedChange(
                                resource_id=db_res.resource_id,
                                resource_name=db_res.name,
                                resource_type=db_res.resource_type,
                                source_file=db_res.source_file,
                                attribute_path="volumes",
                                current_value=["postgres_data:/var/lib/postgresql/data"],
                                proposed_value=[],
                                action_type="REMOVE",
                            )
                        ],
                        estimated_monthly_cost_before="25.00",
                        estimated_monthly_cost_after="0.00",
                        estimated_monthly_savings="25.00",
                        security_impact=ImpactLevel.NEUTRAL,
                        reliability_impact=ImpactLevel.HIGH_NEGATIVE,
                        operational_complexity=OperationalComplexity.HIGH,
                        assumptions=["Database is purely temporary cache (FATAL ASSUMPTION)"],
                        evidence={"resource": db_res.name, "rule": "ANTI-PATTERN"},
                        applicability=ApplicabilityStatus.APPLICABLE,
                        reversibility="LOW",
                    )
                )

            # Flawed candidate 2: Expose internal service to 0.0.0.0/0 to save VPN gateway cost (violates CONST-SEC-01)
            if db_res:
                candidates.append(
                    Candidate(
                        candidate_id=f"cand-unsafe-expose-db-{db_res.name}",
                        title=f"Direct internet binding for {db_res.name} to eliminate VPN infrastructure",
                        description="Insecure cost-cutting measure opening database port 5432 to 0.0.0.0/0 to bypass bastion/VPN costs.",
                        candidate_type=CandidateType.DISABLE_AUTH,
                        affected_resource_ids=[db_res.resource_id],
                        proposed_changes=[
                            ProposedChange(
                                resource_id=db_res.resource_id,
                                resource_name=db_res.name,
                                resource_type=db_res.resource_type,
                                source_file=db_res.source_file,
                                attribute_path="ports",
                                current_value=["127.0.0.1:5432:5432"],
                                proposed_value=["0.0.0.0:5432:5432"],
                                action_type="MODIFY",
                            )
                        ],
                        estimated_monthly_cost_before="35.00",
                        estimated_monthly_cost_after="5.00",
                        estimated_monthly_savings="30.00",
                        security_impact=ImpactLevel.HIGH_NEGATIVE,
                        reliability_impact=ImpactLevel.NEUTRAL,
                        operational_complexity=OperationalComplexity.LOW,
                        assumptions=["Database security rely entirely on application layer passwords"],
                        evidence={"resource": db_res.name, "rule": "ANTI-PATTERN"},
                        applicability=ApplicabilityStatus.APPLICABLE,
                        reversibility="HIGH",
                    )
                )

        # Deduplicate candidates by candidate_id deterministically
        unique_candidates: Dict[str, Candidate] = {}
        for c in candidates:
            if c.candidate_id not in unique_candidates:
                unique_candidates[c.candidate_id] = c

        return list(unique_candidates.values())

    # --- Helper Builders ---

    def _find_resource_for_finding(self, finding: Finding, inventory: InfrastructureInventory) -> Optional[DiscoveredResource]:
        """Match finding to target resource by name or source file."""
        for r in inventory.resources:
            if r.name in finding.title or r.name in finding.description:
                return r
            if r.source_file == finding.source_file:
                # Secondary check: type match
                if "aws_instance" in str(finding.observed_value) or "m5.large" in str(finding.observed_value):
                    if r.resource_type == "aws_instance":
                        return r
                if "io2" in str(finding.observed_value) and r.resource_type == "aws_ebs_volume":
                    return r
                if "postgres" in str(finding.observed_value) and "db" in r.resource_type:
                    return r
        # Fallback to first resource in source file
        matching_file = [r for r in inventory.resources if r.source_file == finding.source_file]
        return matching_file[0] if matching_file else None

    def _create_ec2_resize_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        current_type = str(res.attributes_known.get("instance_type", "m5.large")).lower()
        target_type = "t3.small"

        current_rate = self.catalog.get_rate_for_sku(f"aws_instance:{current_type}")
        target_rate = self.catalog.get_rate_for_sku(f"aws_instance:{target_type}")

        unit_before = current_rate.unit_price if current_rate else Decimal("0.0960")
        unit_after = target_rate.unit_price if target_rate else Decimal("0.0208")

        cost_before = (unit_before * self.monthly_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        cost_after = (unit_after * self.monthly_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        savings = (cost_before - cost_after).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return Candidate(
            candidate_id=f"cand-resize-ec2-{res.name}",
            title=f"Rightsize EC2 '{res.name}' from {current_type} to {target_type}",
            description=f"Downscale staging compute instance from {current_type} to {target_type} to eliminate idle multi-core capacity.",
            candidate_type=CandidateType.RESIZE_COMPUTE,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="instance_type",
                    current_value=current_type,
                    proposed_value=target_type,
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before=str(cost_before),
            estimated_monthly_cost_after=str(cost_after),
            estimated_monthly_savings=str(savings),
            security_impact=ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Staging CPU peak utilization remains <= 2 vCPU"],
            evidence={"current_type": current_type, "target_type": target_type, "unit_savings_per_hr": str(unit_before - unit_after)},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_ebs_downgrade_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        current_type = str(res.attributes_known.get("type", "io2")).lower()
        size_gb = Decimal(str(res.attributes_known.get("size", 100)))
        target_type = "gp3"

        rate_before = self.catalog.get_rate_for_sku("aws_ebs_volume:io2")
        rate_after = self.catalog.get_rate_for_sku("aws_ebs_volume:gp3")

        unit_before = rate_before.unit_price if rate_before else Decimal("0.1250")
        unit_after = rate_after.unit_price if rate_after else Decimal("0.0800")

        cost_before = (unit_before * size_gb).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        cost_after = (unit_after * size_gb).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        savings = (cost_before - cost_after).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return Candidate(
            candidate_id=f"cand-storage-gp3-{res.name}",
            title=f"Migrate volume '{res.name}' from {current_type} to gp3 General Purpose SSD",
            description="Replace expensive provisioned IOPS SSD with gp3 baseline storage providing 3,000 IOPS included.",
            candidate_type=CandidateType.DOWNGRADE_STORAGE,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="type",
                    current_value=current_type,
                    proposed_value=target_type,
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before=str(cost_before),
            estimated_monthly_cost_after=str(cost_after),
            estimated_monthly_savings=str(savings),
            security_impact=ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Staging workload does not exceed 3,000 baseline IOPS"],
            evidence={"size_gb": str(size_gb), "current_type": current_type, "target_type": target_type},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_db_schedule_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        iclass = str(res.attributes_known.get("instance_class", "db.m5.large")).lower()
        rate = self.catalog.get_rate_for_sku(f"aws_db_instance:{iclass}")
        unit = rate.unit_price if rate else Decimal("0.1360")

        # 730h continuous vs 250h off-hours schedule
        cost_before = (unit * Decimal("730")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        cost_after = (unit * Decimal("250")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        savings = (cost_before - cost_after).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return Candidate(
            candidate_id=f"cand-schedule-db-{res.name}",
            title=f"Implement off-hours shutdown schedule on database '{res.name}'",
            description="Automate non-production database shutdown during nights and weekends (~250h/month runtime).",
            candidate_type=CandidateType.SCHEDULE_DATABASE,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="operating_schedule",
                    current_value="24x7 (730h)",
                    proposed_value="working_hours_only (250h)",
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before=str(cost_before),
            estimated_monthly_cost_after=str(cost_after),
            estimated_monthly_savings=str(savings),
            security_impact=ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.MEDIUM,
            assumptions=["Staging tests do not execute between 8pm and 7am local time"],
            evidence={"instance_class": iclass, "monthly_hours_before": 730, "monthly_hours_after": 250},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_container_limits_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-limits-{res.name}",
            title=f"Set CPU and memory resource limits on service '{res.name}'",
            description="Constrain container memory and CPU bounds to prevent host daemon memory exhaustion.",
            candidate_type=CandidateType.SET_RESOURCE_LIMITS,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="deploy.resources.limits",
                    current_value=None,
                    proposed_value={"cpus": "0.5", "memory": "512M"},
                    action_type="ADD",
                )
            ],
            estimated_monthly_cost_before="10.95",
            estimated_monthly_cost_after="10.95",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel.POSITIVE,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Service does not require > 512MB RAM under typical staging load"],
            evidence={"service": res.name},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_isolate_redis_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-isolate-redis-{res.name}",
            title=f"Restrict Redis '{res.name}' binding to 127.0.0.1",
            description="Remove 0.0.0.0 public interface exposure and bind Redis strictly to localhost container bridge.",
            candidate_type=CandidateType.ISOLATE_SERVICE,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="ports",
                    current_value=["0.0.0.0:6379:6379"],
                    proposed_value=["127.0.0.1:6379:6379"],
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.HIGH_POSITIVE,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["No external clients outside host require direct Redis port exposure"],
            evidence={"ports": res.attributes_known.get("ports", [])},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_isolate_db_port_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-isolate-db-{res.name}",
            title=f"Remove public host port publishing for database '{res.name}'",
            description="Remove public 0.0.0.0 host port binding and restrict database communication to Docker overlay network.",
            candidate_type=CandidateType.ISOLATE_SERVICE,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="ports",
                    current_value=["0.0.0.0:5432:5432"],
                    proposed_value=[],
                    action_type="REMOVE",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.HIGH_POSITIVE,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Backend services communicate with database via Docker bridge DNS name"],
            evidence={"ports": res.attributes_known.get("ports", [])},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_restrict_ingress_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-restrict-ingress-{res.name}",
            title=f"Restrict 0.0.0.0/0 ingress on Security Group '{res.name}'",
            description="Replace unrestricted public internet ingress with internal VPN CIDR block (10.0.1.0/24).",
            candidate_type=CandidateType.RESTRICT_INGRESS,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="ingress.cidr_blocks",
                    current_value=["0.0.0.0/0"],
                    proposed_value=["10.0.1.0/24"],
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.HIGH_POSITIVE,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.MEDIUM,
            assumptions=["Developers access administrative interfaces via VPN or bastion"],
            evidence={"security_group": res.name},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_remove_privileged_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-remove-privilege-{res.name}",
            title=f"Disable privileged execution mode on service '{res.name}'",
            description="Remove `privileged: true` to enforce container namespace isolation and host protection.",
            candidate_type=CandidateType.REMOVE_PRIVILEGED,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="privileged",
                    current_value=True,
                    proposed_value=False,
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.HIGH_POSITIVE,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Service does not require kernel module manipulation"],
            evidence={"privileged": True},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_remove_socket_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-remove-socket-{res.name}",
            title=f"Remove Docker socket mount from service '{res.name}'",
            description="Detach `/var/run/docker.sock` to prevent unauthorized root daemon control.",
            candidate_type=CandidateType.REMOVE_DOCKER_SOCKET,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="volumes",
                    current_value=["/var/run/docker.sock:/var/run/docker.sock"],
                    proposed_value=[],
                    action_type="REMOVE",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.HIGH_POSITIVE,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.MEDIUM,
            assumptions=["Process management does not require sibling container orchestration"],
            evidence={"mounted_volume": "/var/run/docker.sock"},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_s3_secure_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-secure-s3-{res.name}",
            title=f"Enforce private ACL and Public Access Block on S3 bucket '{res.name}'",
            description="Set bucket ACL to private and attach aws_s3_bucket_public_access_block.",
            candidate_type=CandidateType.ISOLATE_SERVICE,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="acl",
                    current_value="public-read",
                    proposed_value="private",
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before="1.15",
            estimated_monthly_cost_after="1.15",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.HIGH_POSITIVE,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Public web assets served through CloudFront origin access control"],
            evidence={"bucket": res.name},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_enable_encryption_candidate(self, res: DiscoveredResource, finding: Finding, label: str) -> Candidate:
        attr = "storage_encrypted" if "db" in res.resource_type else "encrypted"
        return Candidate(
            candidate_id=f"cand-encrypt-{res.name}",
            title=f"Enable KMS encryption at rest on {label} '{res.name}'",
            description=f"Enforce server-side KMS encryption at rest on {label}.",
            candidate_type=CandidateType.ENABLE_ENCRYPTION,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path=attr,
                    current_value=False,
                    proposed_value=True,
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.POSITIVE,
            reliability_impact=ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["AWS managed KMS key (aws/rds or aws/ebs) is available"],
            evidence={"resource": res.name, "attribute": attr},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_add_healthcheck_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-healthcheck-{res.name}",
            title=f"Configure liveness healthcheck probe on service '{res.name}'",
            description="Declare healthcheck command, interval, and timeout to enable automated failure detection.",
            candidate_type=CandidateType.ADD_HEALTHCHECK,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="healthcheck",
                    current_value=None,
                    proposed_value={"test": ["CMD", "ping"], "interval": "10s", "timeout": "3s", "retries": 3},
                    action_type="ADD",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel.POSITIVE,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Container image includes required diagnostic command"],
            evidence={"service": res.name},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_set_restart_policy_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-restart-{res.name}",
            title=f"Configure 'restart: unless-stopped' on service '{res.name}'",
            description="Ensure autonomous container recovery following host reboots or unexpected process termination.",
            candidate_type=CandidateType.SET_RESTART_POLICY,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="restart",
                    current_value="no",
                    proposed_value="unless-stopped",
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel.POSITIVE,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Container does not fail in an unrecoverable crash loop"],
            evidence={"service": res.name},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_multiaz_upgrade_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        iclass = str(res.attributes_known.get("instance_class", "db.m5.large")).lower()
        rate = self.catalog.get_rate_for_sku(f"aws_db_instance:{iclass}")
        single_az_unit = rate.unit_price if rate else Decimal("0.1360")
        multi_az_unit = single_az_unit * Decimal("2")

        cost_before = (single_az_unit * self.monthly_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        cost_after = (multi_az_unit * self.monthly_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        savings = (cost_before - cost_after).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)  # Negative = cost increase

        return Candidate(
            candidate_id=f"cand-multiaz-{res.name}",
            title=f"Upgrade database '{res.name}' to Multi-AZ high availability",
            description="Enable synchronous standby replica in a second Availability Zone to provide automated failover.",
            candidate_type=CandidateType.MULTI_AZ_FAILOVER,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="multi_az",
                    current_value=False,
                    proposed_value=True,
                    action_type="MODIFY",
                )
            ],
            estimated_monthly_cost_before=str(cost_before),
            estimated_monthly_cost_after=str(cost_after),
            estimated_monthly_savings=str(savings),
            security_impact=ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel.HIGH_POSITIVE,
            operational_complexity=OperationalComplexity.MEDIUM,
            assumptions=["Target VPC contains subnets in at least two distinct AZs"],
            evidence={"single_az_cost": str(cost_before), "multi_az_cost": str(cost_after)},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )

    def _create_add_volume_candidate(self, res: DiscoveredResource, finding: Finding) -> Candidate:
        return Candidate(
            candidate_id=f"cand-volume-{res.name}",
            title=f"Attach persistent named volume to stateful service '{res.name}'",
            description="Configure persistent Docker volume to preserve application state across container updates.",
            candidate_type=CandidateType.ADD_PERSISTENT_VOLUME,
            affected_resource_ids=[res.resource_id],
            source_finding_ids=[finding.finding_id],
            proposed_changes=[
                ProposedChange(
                    resource_id=res.resource_id,
                    resource_name=res.name,
                    resource_type=res.resource_type,
                    source_file=res.source_file,
                    attribute_path="volumes",
                    current_value=[],
                    proposed_value=[f"{res.name}_data:/var/lib/data"],
                    action_type="ADD",
                )
            ],
            estimated_monthly_cost_before="0.00",
            estimated_monthly_cost_after="0.00",
            estimated_monthly_savings="0.00",
            security_impact=ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel.HIGH_POSITIVE,
            operational_complexity=OperationalComplexity.LOW,
            assumptions=["Host storage has adequate local disk capacity"],
            evidence={"service": res.name},
            applicability=ApplicabilityStatus.APPLICABLE,
            reversibility="HIGH",
        )
