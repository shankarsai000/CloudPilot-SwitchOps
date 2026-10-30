"""
CloudPilot SwitchOps — Unit Tests: FinOps Engine & Pricing Catalog

Tests Decimal monetary arithmetic, pricing catalog lookups, calculation breakdowns,
and financial hygiene rule triggers (FIN-001 through FIN-005).
"""

from decimal import Decimal
import pytest

from app.domain.finding import FindingCategory
from app.services.discovery.engine import InfrastructureDiscoveryEngine
from app.services.finops.catalog import PricingCatalog
from app.services.finops.engine import FinOpsEngine


class TestFinOpsCatalog:
    """Verifies catalog loading, schema validation, and rate lookups."""

    def test_catalog_loading_and_provenance(self) -> None:
        catalog = PricingCatalog()
        assert catalog.catalog_version == "1.0"
        assert catalog.currency == "USD"
        assert catalog.standard_monthly_hours == 730
        assert len(catalog._rates_by_sku) >= 15
        assert "CloudPilot SwitchOps" in catalog.provenance.get("source", "")

    def test_sku_lookups(self) -> None:
        catalog = PricingCatalog()
        ec2_entry = catalog.get_rate_for_sku("aws_instance:m5.large")
        assert ec2_entry is not None
        assert ec2_entry.unit_price == Decimal("0.0960")
        assert ec2_entry.pricing_unit == "hour"

        ebs_entry = catalog.get_rate_for_sku("aws_ebs_volume:gp3")
        assert ebs_entry is not None
        assert ebs_entry.unit_price == Decimal("0.0800")


class TestFinOpsEngine:
    """Verifies baseline monthly cost estimation and FinOps rules."""

    def test_finops_analysis_on_staging(self) -> None:
        engine_disc = InfrastructureDiscoveryEngine()
        inventory = engine_disc.discover_workspace("samples/staging", task_id="finops-test-task")

        finops = FinOpsEngine(monthly_hours=730)
        result = finops.analyze(inventory=inventory, task_id="finops-test-task")

        assert result.task_id == "finops-test-task"
        assert Decimal(result.total_monthly_cost) > Decimal("50.00")
        assert result.currency == "USD"
        assert len(result.items) >= 5

        # Check FinOps findings
        rule_ids = [f.rule_id for f in result.findings]
        assert "FIN-001" in rule_ids  # Oversized m5.large instance
        assert "FIN-005" in rule_ids  # io2 storage volume
        assert "FIN-003" in rule_ids  # Always-on RDS
        assert "FIN-002" in rule_ids  # Missing compose limits

        # Verify FIN-001 content
        f_fin1 = next(f for f in result.findings if f.rule_id == "FIN-001")
        assert f_fin1.category == FindingCategory.FINOPS
        assert f_fin1.agent_id == "finops-specialist"
        assert "m5.large" in f_fin1.title

    def test_finops_analysis_on_safe(self) -> None:
        engine_disc = InfrastructureDiscoveryEngine()
        inventory = engine_disc.discover_workspace("samples/safe", task_id="finops-safe-task")

        finops = FinOpsEngine(monthly_hours=730)
        result = finops.analyze(inventory=inventory, task_id="finops-safe-task")

        rule_ids = [f.rule_id for f in result.findings]
        # Safe environment rightsized to t3.micro -> FIN-001 should NOT trigger
        assert "FIN-001" not in rule_ids
        # Safe environment uses gp3 -> FIN-005 should NOT trigger
        assert "FIN-005" not in rule_ids
        # Total cost should be significantly lower than staging
        assert Decimal(result.total_monthly_cost) < Decimal("50.00")
