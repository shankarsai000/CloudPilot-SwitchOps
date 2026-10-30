"""
CloudPilot SwitchOps — FinOps Intelligence Engine

Performs deterministic, evidence-backed cloud infrastructure cost estimation
and financial hygiene analysis using versioned pricing catalogs and Decimal arithmetic.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.domain.finding import Finding, FindingCategory, FindingSeverity
from app.domain.inventory import DiscoveredResource, InfrastructureInventory
from app.services.finops.catalog import PricingCatalog

logger = logging.getLogger("cloudpilot.finops.engine")

TWO_PLACES = Decimal("0.01")


class ResourceCostBreakdown(BaseModel):
    """Itemized monthly cost estimation for an individual discovered resource."""
    resource_id: str
    resource_name: str
    resource_type: str
    provider: str
    sku: str
    unit_price: str
    pricing_unit: str
    monthly_units: str
    monthly_cost: str
    currency: str = "USD"
    notes: str = ""
    is_estimated: bool = False


class FinOpsAnalysisResult(BaseModel):
    """Consolidated cost breakdown and financial hygiene analysis outcome."""
    task_id: Optional[str] = None
    workspace_root: str
    total_monthly_cost: str
    currency: str = "USD"
    monthly_hours: int = 730
    items: List[ResourceCostBreakdown] = Field(default_factory=list)
    findings: List[Finding] = Field(default_factory=list)
    summary_text: str = ""


class FinOpsEngine:
    """
    Deterministic cost calculator and FinOps rule evaluator.
    Strictly uses Decimal arithmetic to eliminate IEEE-754 floating point drift.
    """

    def __init__(
        self,
        catalog: Optional[PricingCatalog] = None,
        monthly_hours: int = 730,
    ) -> None:
        self.catalog = catalog or PricingCatalog()
        self.monthly_hours = Decimal(str(monthly_hours))
        self.currency = self.catalog.currency

    def analyze(
        self,
        inventory: InfrastructureInventory,
        task_id: str = "task-local",
    ) -> FinOpsAnalysisResult:
        """
        Calculates itemized and consolidated monthly costs and runs FinOps rules.
        """
        items: List[ResourceCostBreakdown] = []
        findings: List[Finding] = []
        total_monthly = Decimal("0.00")

        for res in inventory.resources:
            cost_item, res_findings = self._evaluate_resource_cost_and_findings(res, task_id)
            if cost_item:
                items.append(cost_item)
                item_dec = Decimal(cost_item.monthly_cost)
                total_monthly = (total_monthly + item_dec).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            findings.extend(res_findings)

        # Build high-level summary narrative
        summary_text = (
            f"Estimated monthly infrastructure baseline is ${total_monthly} {self.currency} "
            f"across {len(items)} billable resources (based on {self.monthly_hours} hours/month). "
            f"Identified {len(findings)} financial hygiene finding(s)."
        )

        return FinOpsAnalysisResult(
            task_id=task_id,
            workspace_root=inventory.workspace_root,
            total_monthly_cost=str(total_monthly),
            currency=self.currency,
            monthly_hours=int(self.monthly_hours),
            items=items,
            findings=findings,
            summary_text=summary_text,
        )

    def _evaluate_resource_cost_and_findings(
        self,
        resource: DiscoveredResource,
        task_id: str,
    ) -> tuple[Optional[ResourceCostBreakdown], List[Finding]]:
        """Compute cost and inspect financial hygiene for a single resource."""
        findings: List[Finding] = []
        rtype = resource.resource_type.lower()
        provider = resource.provider.lower()
        known = resource.attributes_known

        # Check for unknown attributes that impede exact pricing (FIN-004)
        if resource.attributes_unknown:
            pricing_affecting = [
                attr for attr in resource.attributes_unknown
                if any(k in attr.lower() for k in ["instance", "type", "size", "sku", "capacity", "count"])
            ]
            if pricing_affecting:
                findings.append(
                    Finding(
                        task_id=task_id,
                        agent_id="finops-specialist",
                        category=FindingCategory.FINOPS,
                        rule_id="FIN-004",
                        severity=FindingSeverity.LOW,
                        title=f"Dynamic or unresolved pricing input in {resource.name}",
                        description=(
                            f"Resource '{resource.name}' ({resource.resource_type}) uses dynamic/variable expressions "
                            f"for attributes {pricing_affecting}, requiring baseline estimation fallback."
                        ),
                        source_file=resource.source_file,
                        source_location=resource.source_location,
                        observed_value=pricing_affecting,
                        expected_value="Static or statically resolvable sizing values in declarative config",
                        evidence={"unknown_attributes": resource.attributes_unknown, "resource_name": resource.name},
                        recommendation="Pin explicit sizing configurations or provide static staging tfvars.",
                        confidence=0.90,
                    )
                )

        cost_item: Optional[ResourceCostBreakdown] = None

        if rtype == "aws_instance":
            cost_item, ec2_findings = self._calculate_ec2(resource, task_id)
            findings.extend(ec2_findings)
        elif rtype == "aws_ebs_volume":
            cost_item, ebs_findings = self._calculate_ebs(resource, task_id)
            findings.extend(ebs_findings)
        elif rtype in ("aws_db_instance", "aws_rds_cluster_instance"):
            cost_item, rds_findings = self._calculate_rds(resource, task_id)
            findings.extend(rds_findings)
        elif rtype in ("aws_s3_bucket", "aws_s3_bucket_v2"):
            cost_item = self._calculate_s3(resource)
        elif rtype in ("aws_lb", "aws_alb"):
            cost_item = self._calculate_alb(resource)
        elif provider == "docker" and rtype == "compose_service":
            cost_item, compose_findings = self._calculate_compose(resource, task_id)
            findings.extend(compose_findings)

        return cost_item, findings

    def _calculate_ec2(
        self,
        resource: DiscoveredResource,
        task_id: str,
    ) -> tuple[ResourceCostBreakdown, List[Finding]]:
        findings: List[Finding] = []
        known = resource.attributes_known
        instance_type = str(known.get("instance_type", "t3.micro")).lower()

        # Rule FIN-001: Oversized instance check
        oversized_instances = ["m5.large", "c5.xlarge", "m5.xlarge", "r5.large", "c5.2xlarge"]
        if instance_type in oversized_instances:
            findings.append(
                Finding(
                    task_id=task_id,
                    agent_id="finops-specialist",
                    category=FindingCategory.FINOPS,
                    rule_id="FIN-001",
                    severity=FindingSeverity.MEDIUM,
                    title=f"Potentially oversized compute instance '{instance_type}' in non-production",
                    description=(
                        f"Instance '{resource.name}' is declared as '{instance_type}'. "
                        f"Staging and testing workloads rarely require general-purpose multi-core instances, "
                        f"incurring unnecessary monthly spend."
                    ),
                    source_file=resource.source_file,
                    source_location=resource.source_location,
                    observed_value=instance_type,
                    expected_value="t3.small or t3.medium for staging",
                    evidence={"instance_type": instance_type, "resource_name": resource.name},
                    recommendation=f"Downscale '{instance_type}' to 't3.small' or 't3.medium' to reduce idle compute costs.",
                    confidence=0.85,
                )
            )

        sku = f"aws_instance:{instance_type}"
        rate_entry = self.catalog.get_rate_for_sku(sku) or self.catalog.get_rate_for_sku("aws_instance:t3.micro")

        unit_price = rate_entry.unit_price if rate_entry else Decimal("0.0104")
        monthly_cost = (unit_price * self.monthly_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        item = ResourceCostBreakdown(
            resource_id=resource.resource_id,
            resource_name=resource.name,
            resource_type=resource.resource_type,
            provider="aws",
            sku=rate_entry.sku if rate_entry else sku,
            unit_price=str(unit_price),
            pricing_unit="hour",
            monthly_units=str(self.monthly_hours),
            monthly_cost=str(monthly_cost),
            currency=self.currency,
            notes=f"EC2 on-demand ({instance_type})",
            is_estimated=(rate_entry is None or sku not in self.catalog._rates_by_sku),
        )
        return item, findings

    def _calculate_ebs(
        self,
        resource: DiscoveredResource,
        task_id: str,
    ) -> tuple[ResourceCostBreakdown, List[Finding]]:
        findings: List[Finding] = []
        known = resource.attributes_known
        vol_type = str(known.get("type", "gp3")).lower()
        size_val = known.get("size", 20)
        try:
            size_gb = Decimal(str(size_val))
        except Exception:
            size_gb = Decimal("20")

        # Rule FIN-005: Expensive provisioned IOPS in staging
        if vol_type in ("io1", "io2"):
            findings.append(
                Finding(
                    task_id=task_id,
                    agent_id="finops-specialist",
                    category=FindingCategory.FINOPS,
                    rule_id="FIN-005",
                    severity=FindingSeverity.MEDIUM,
                    title=f"Costly Provisioned IOPS ({vol_type}) storage volume on {resource.name}",
                    description=(
                        f"Volume '{resource.name}' is configured as '{vol_type}' provisioned IOPS SSD. "
                        f"Provisioned IOPS carries significant hourly and capacity surcharges. "
                        f"General Purpose gp3 provides 3,000 baseline IOPS at a fraction of the cost."
                    ),
                    source_file=resource.source_file,
                    source_location=resource.source_location,
                    observed_value=vol_type,
                    expected_value="gp3",
                    evidence={"volume_type": vol_type, "size_gb": str(size_gb), "resource": resource.name},
                    recommendation="Migrate volume from io2 to gp3 SSD storage to eliminate unneeded IOPS charges.",
                    confidence=0.95,
                )
            )

        sku = f"aws_ebs_volume:{vol_type}"
        rate_entry = self.catalog.get_rate_for_sku(sku) or self.catalog.get_rate_for_sku("aws_ebs_volume:gp3")

        unit_price = rate_entry.unit_price if rate_entry else Decimal("0.0800")
        monthly_cost = (unit_price * size_gb).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        item = ResourceCostBreakdown(
            resource_id=resource.resource_id,
            resource_name=resource.name,
            resource_type=resource.resource_type,
            provider="aws",
            sku=rate_entry.sku if rate_entry else sku,
            unit_price=str(unit_price),
            pricing_unit="gb-month",
            monthly_units=str(size_gb),
            monthly_cost=str(monthly_cost),
            currency=self.currency,
            notes=f"EBS {vol_type} ({size_gb} GB)",
            is_estimated=False,
        )
        return item, findings

    def _calculate_rds(
        self,
        resource: DiscoveredResource,
        task_id: str,
    ) -> tuple[ResourceCostBreakdown, List[Finding]]:
        findings: List[Finding] = []
        known = resource.attributes_known
        instance_class = str(known.get("instance_class", "db.t3.micro")).lower()

        # Rule FIN-003: Always-on staging database without off-hours auto-pause
        findings.append(
            Finding(
                task_id=task_id,
                agent_id="finops-specialist",
                category=FindingCategory.FINOPS,
                rule_id="FIN-003",
                severity=FindingSeverity.LOW,
                title=f"Continuous 730h runtime modeled for staging database '{resource.name}'",
                description=(
                    f"RDS instance '{resource.name}' ({instance_class}) runs continuously 24/7 in staging. "
                    f"Implementing scheduled stop/start or Aurora Serverless auto-pause during non-working hours "
                    f"reduces baseline run-rate by up to 65%."
                ),
                source_file=resource.source_file,
                source_location=resource.source_location,
                observed_value=f"Continuous 24/7 ({self.monthly_hours} hours/mo)",
                expected_value="Scheduled off-hours shutdown (~250-300 hours/mo)",
                evidence={"instance_class": instance_class, "monthly_hours": int(self.monthly_hours)},
                recommendation="Apply off-hours shutdown schedule to non-production database instances.",
                confidence=0.80,
            )
        )

        sku = f"aws_db_instance:{instance_class}"
        rate_entry = self.catalog.get_rate_for_sku(sku) or self.catalog.get_rate_for_sku("aws_db_instance:db.t3.micro")

        unit_price = rate_entry.unit_price if rate_entry else Decimal("0.0170")
        monthly_cost = (unit_price * self.monthly_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        item = ResourceCostBreakdown(
            resource_id=resource.resource_id,
            resource_name=resource.name,
            resource_type=resource.resource_type,
            provider="aws",
            sku=rate_entry.sku if rate_entry else sku,
            unit_price=str(unit_price),
            pricing_unit="hour",
            monthly_units=str(self.monthly_hours),
            monthly_cost=str(monthly_cost),
            currency=self.currency,
            notes=f"RDS on-demand ({instance_class})",
            is_estimated=(rate_entry is None or sku not in self.catalog._rates_by_sku),
        )
        return item, findings

    def _calculate_s3(self, resource: DiscoveredResource) -> ResourceCostBreakdown:
        sku = "aws_s3_bucket:standard"
        rate_entry = self.catalog.get_rate_for_sku(sku)
        unit_price = rate_entry.unit_price if rate_entry else Decimal("0.0230")
        # Baseline model assumes 50 GB standard usage
        baseline_gb = Decimal("50")
        monthly_cost = (unit_price * baseline_gb).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return ResourceCostBreakdown(
            resource_id=resource.resource_id,
            resource_name=resource.name,
            resource_type=resource.resource_type,
            provider="aws",
            sku=sku,
            unit_price=str(unit_price),
            pricing_unit="gb-month",
            monthly_units=str(baseline_gb),
            monthly_cost=str(monthly_cost),
            currency=self.currency,
            notes="S3 Standard baseline estimate (50 GB storage)",
            is_estimated=True,
        )

    def _calculate_alb(self, resource: DiscoveredResource) -> ResourceCostBreakdown:
        sku = "aws_lb:application"
        rate_entry = self.catalog.get_rate_for_sku(sku)
        unit_price = rate_entry.unit_price if rate_entry else Decimal("0.0225")
        monthly_cost = (unit_price * self.monthly_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return ResourceCostBreakdown(
            resource_id=resource.resource_id,
            resource_name=resource.name,
            resource_type=resource.resource_type,
            provider="aws",
            sku=sku,
            unit_price=str(unit_price),
            pricing_unit="hour",
            monthly_units=str(self.monthly_hours),
            monthly_cost=str(monthly_cost),
            currency=self.currency,
            notes="Application Load Balancer baseline hourly charge",
            is_estimated=False,
        )

    def _calculate_compose(
        self,
        resource: DiscoveredResource,
        task_id: str,
    ) -> tuple[ResourceCostBreakdown, List[Finding]]:
        findings: List[Finding] = []
        known = resource.attributes_known

        replicas_val = known.get("replicas", 1)
        try:
            replicas = Decimal(str(replicas_val))
        except Exception:
            replicas = Decimal("1")

        has_limits = known.get("has_resource_limits", False)
        limits = known.get("limits", {})

        # Rule FIN-002: Missing resource limits leads to cluster over-allocation and runaway billing
        if not has_limits:
            findings.append(
                Finding(
                    task_id=task_id,
                    agent_id="finops-specialist",
                    category=FindingCategory.FINOPS,
                    rule_id="FIN-002",
                    severity=FindingSeverity.LOW,
                    title=f"Unbounded container resource limits on service '{resource.name}'",
                    description=(
                        f"Docker Compose service '{resource.name}' does not specify CPU or memory limits in deploy.resources. "
                        f"Without explicit resource limits, container memory leaks can exhaust node memory, forcing "
                        f"unexpected autoscaling or larger node instance types."
                    ),
                    source_file=resource.source_file,
                    source_location=resource.source_location,
                    observed_value="deploy.resources.limits is undefined",
                    expected_value="Explicit cpus and memory constraints defined",
                    evidence={"service_name": resource.name, "image": known.get("image", "unknown")},
                    recommendation="Set explicit `deploy.resources.limits` (e.g. cpus: '0.5', memory: '512M') in Compose.",
                    confidence=0.90,
                )
            )

        # Rate determination based on sizing
        is_medium = False
        if limits:
            cpu_val = str(limits.get("cpus", "1"))
            try:
                if float(cpu_val) > 1.0:
                    is_medium = True
            except ValueError:
                pass

        sku = "compose_service:compute_medium" if is_medium else "compose_service:compute_small"
        rate_entry = self.catalog.get_rate_for_sku(sku)
        unit_price = rate_entry.unit_price if rate_entry else Decimal("0.0150")

        total_hours = self.monthly_hours * replicas
        monthly_cost = (unit_price * total_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        item = ResourceCostBreakdown(
            resource_id=resource.resource_id,
            resource_name=resource.name,
            resource_type=resource.resource_type,
            provider="docker",
            sku=sku,
            unit_price=str(unit_price),
            pricing_unit="hour",
            monthly_units=str(total_hours),
            monthly_cost=str(monthly_cost),
            currency=self.currency,
            notes=f"Container service ({replicas} replica(s))",
            is_estimated=True,
        )
        return item, findings
