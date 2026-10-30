"""
CloudPilot SwitchOps — Unit Tests: Infrastructure Discovery Parsers & Engine

Tests filesystem security bounds, path traversal protection, HCL parsing,
Docker Compose YAML parsing, and normalized inventory assembly.
"""

from pathlib import Path
import pytest

from app.core.errors import ValidationError
from app.domain.inventory import ResourceCategory
from app.services.discovery.compose_parser import ComposeParser
from app.services.discovery.engine import InfrastructureDiscoveryEngine
from app.services.discovery.terraform_parser import TerraformParser


class TestTerraformParser:
    """Verifies HCL2 parsing and normalization into DiscoveredResource domain models."""

    def test_parse_staging_terraform(self) -> None:
        parser = TerraformParser()
        tf_file = Path("samples/staging/main.tf")
        assert tf_file.exists()

        resources = parser.parse_file(tf_file, workspace_root="samples/staging")
        assert len(resources) >= 5

        # Verify EC2 instance
        ec2_res = next((r for r in resources if r.resource_type == "aws_instance"), None)
        assert ec2_res is not None
        assert ec2_res.provider == "aws"
        assert ec2_res.category == ResourceCategory.COMPUTE
        assert ec2_res.attributes_known.get("instance_type") == "m5.large"

        # Verify EBS volume
        ebs_res = next((r for r in resources if r.resource_type == "aws_ebs_volume"), None)
        assert ebs_res is not None
        assert ebs_res.category == ResourceCategory.STORAGE
        assert ebs_res.attributes_known.get("type") == "io2"
        assert ebs_res.attributes_known.get("encrypted") is False

        # Verify RDS instance
        rds_res = next((r for r in resources if r.resource_type == "aws_db_instance"), None)
        assert rds_res is not None
        assert rds_res.category == ResourceCategory.DATABASE
        assert rds_res.attributes_known.get("instance_class") == "db.m5.large"
        assert rds_res.attributes_known.get("storage_encrypted") is False
        assert rds_res.attributes_known.get("multi_az") is False

        # Verify Security Group
        sg_res = next((r for r in resources if r.resource_type == "aws_security_group"), None)
        assert sg_res is not None
        assert sg_res.category == ResourceCategory.SECURITY

    def test_parse_dynamic_expressions_tracked_as_unknown(self) -> None:
        parser = TerraformParser()
        safe_file = Path("samples/safe/main.tf")
        assert safe_file.exists()

        resources = parser.parse_file(safe_file, workspace_root="samples/safe")
        rds_res = next((r for r in resources if r.resource_type == "aws_db_instance"), None)
        assert rds_res is not None
        # Password was "${var.db_secret_vault_reference}" -> should be recorded in attributes_unknown
        assert "password" in rds_res.attributes_unknown

    def test_parse_empty_or_non_hcl_file(self, tmp_path: Path) -> None:
        parser = TerraformParser()
        empty_tf = tmp_path / "empty.tf"
        empty_tf.write_text("# Just comments\n", encoding="utf-8")
        resources = parser.parse_file(empty_tf, workspace_root=str(tmp_path))
        assert resources == []


class TestComposeParser:
    """Verifies Docker Compose safe YAML parsing, volume mapping, and secret redaction."""

    def test_parse_staging_compose(self) -> None:
        parser = ComposeParser()
        compose_file = Path("samples/staging/docker-compose.yml")
        assert compose_file.exists()

        resources = parser.parse_file(compose_file, workspace_root="samples/staging")
        assert len(resources) == 3

        service_names = [r.name for r in resources]
        assert "redis" in service_names
        assert "postgres" in service_names
        assert "admin_daemon" in service_names

        # Verify Redis details
        redis_res = next(r for r in resources if r.name == "redis")
        assert redis_res.category in (ResourceCategory.CONTAINER, ResourceCategory.DATABASE)
        assert redis_res.provider == "docker"
        ports = redis_res.attributes_known.get("ports", [])
        assert any("6379" in str(p) for p in ports)

        # Verify Postgres secret redaction
        pg_res = next(r for r in resources if r.name == "postgres")
        env = pg_res.attributes_known.get("environment", {})
        assert env.get("POSTGRES_PASSWORD") == "[REDACTED]"

        # Verify Admin Daemon dangerous capabilities
        admin_res = next(r for r in resources if r.name == "admin_daemon")
        assert admin_res.attributes_known.get("privileged") is True
        assert admin_res.attributes_known.get("network_mode") == "host"
        assert any("docker.sock" in str(v) for v in admin_res.attributes_known.get("volumes", []))


class TestInfrastructureDiscoveryEngine:
    """Verifies filesystem security protections and inventory compilation."""

    def test_discover_staging_inventory(self) -> None:
        engine = InfrastructureDiscoveryEngine()
        inventory = engine.discover_workspace("samples/staging", task_id="test-task-1")

        assert inventory.task_id == "test-task-1"
        assert inventory.total_resources >= 8
        assert len(inventory.discovered_files) >= 2
        assert inventory.discovery_duration_ms > 0

    def test_path_traversal_rejection(self, tmp_path: Path) -> None:
        engine = InfrastructureDiscoveryEngine()
        # Attempt to escape allowed base
        allowed = tmp_path / "allowed_root"
        allowed.mkdir()

        with pytest.raises(ValidationError) as exc_info:
            engine.validate_workspace_path("../outside", allowed_base=allowed)
        assert "Path traversal violation" in str(exc_info.value)

    def test_nonexistent_workspace_rejection(self) -> None:
        engine = InfrastructureDiscoveryEngine()
        with pytest.raises(ValidationError) as exc_info:
            engine.discover_workspace("samples/non_existent_folder_xyz")
        assert "does not exist" in str(exc_info.value)
