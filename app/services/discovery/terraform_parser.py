"""
CloudPilot SwitchOps — Terraform HCL Parser

Parses Terraform (.tf and .tfvars) configuration files without executing terraform binaries.
Extracts declared cloud resources, isolates known static attributes from dynamic expressions,
and maps them to canonical DiscoveredResource instances.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import hcl2

from app.domain.inventory import DiscoveredResource, ResourceCategory

logger = logging.getLogger("cloudpilot.discovery.terraform")

# Categorization mapping for common Terraform resource types
RESOURCE_CATEGORY_MAP: Dict[str, ResourceCategory] = {
    # Compute
    "aws_instance": ResourceCategory.COMPUTE,
    "aws_launch_template": ResourceCategory.COMPUTE,
    "aws_launch_configuration": ResourceCategory.COMPUTE,
    "aws_autoscaling_group": ResourceCategory.COMPUTE,
    "aws_ecs_task_definition": ResourceCategory.COMPUTE,
    "aws_ecs_service": ResourceCategory.COMPUTE,
    "aws_lambda_function": ResourceCategory.COMPUTE,
    "azurerm_linux_virtual_machine": ResourceCategory.COMPUTE,
    "azurerm_windows_virtual_machine": ResourceCategory.COMPUTE,
    # Storage
    "aws_ebs_volume": ResourceCategory.STORAGE,
    "aws_s3_bucket": ResourceCategory.STORAGE,
    "aws_s3_bucket_public_access_block": ResourceCategory.SECURITY,
    "aws_s3_bucket_server_side_encryption_configuration": ResourceCategory.SECURITY,
    "azurerm_storage_account": ResourceCategory.STORAGE,
    # Database
    "aws_db_instance": ResourceCategory.DATABASE,
    "aws_rds_cluster": ResourceCategory.DATABASE,
    "aws_dynamodb_table": ResourceCategory.DATABASE,
    "azurerm_sql_database": ResourceCategory.DATABASE,
    # Network
    "aws_vpc": ResourceCategory.NETWORK,
    "aws_subnet": ResourceCategory.NETWORK,
    "aws_lb": ResourceCategory.NETWORK,
    "aws_alb": ResourceCategory.NETWORK,
    "aws_elb": ResourceCategory.NETWORK,
    "aws_internet_gateway": ResourceCategory.NETWORK,
    "aws_nat_gateway": ResourceCategory.NETWORK,
    "aws_route_table": ResourceCategory.NETWORK,
    # Security
    "aws_security_group": ResourceCategory.SECURITY,
    "aws_security_group_rule": ResourceCategory.SECURITY,
    "aws_iam_role": ResourceCategory.SECURITY,
    "aws_iam_policy": ResourceCategory.SECURITY,
    "azurerm_network_security_group": ResourceCategory.SECURITY,
}


def _clean_value(val: Any) -> Any:
    """Recursively strip surrounding quotes and internal block markers from HCL output."""
    if isinstance(val, str):
        cleaned = val.strip()
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1]
        return cleaned
    if isinstance(val, dict):
        return {
            _clean_value(k): _clean_value(v)
            for k, v in val.items()
            if k != "__is_block__"
        }
    if isinstance(val, list):
        return [_clean_value(item) for item in val if item != "__is_block__"]
    return val


def _is_dynamic_expression(val: Any) -> bool:
    """Detect whether a parsed attribute represents an unresolved dynamic expression or variable."""
    if isinstance(val, str):
        v = val.strip()
        return v.startswith("${") and v.endswith("}")
    return False


def _separate_known_and_unknown(config: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Separate verified static literal attributes from dynamic/unknown expressions."""
    known: Dict[str, Any] = {}
    unknown: List[str] = []

    for k, v in config.items():
        if _is_dynamic_expression(v):
            unknown.append(k)
        elif isinstance(v, dict):
            sub_known, sub_unknown = _separate_known_and_unknown(v)
            if sub_known:
                known[k] = sub_known
            if sub_unknown:
                unknown.extend([f"{k}.{uk}" for uk in sub_unknown])
        elif isinstance(v, list):
            has_unknown = any(_is_dynamic_expression(item) for item in v)
            if has_unknown:
                unknown.append(k)
            else:
                known[k] = v
        else:
            known[k] = v

    return known, unknown


class TerraformParser:
    """Parses Terraform HCL content safely into DiscoveredResource models."""

    def parse_hcl_content(self, content: str, source_file: str) -> List[DiscoveredResource]:
        """
        Parse raw HCL string and extract declared resources.
        Returns empty list on non-resource or syntax errors, logging the condition safely.
        """
        if not content.strip():
            return []

        try:
            parsed = hcl2.loads(content)
        except Exception as exc:
            logger.warning("Failed to parse HCL in '%s': %s", source_file, exc)
            return []

        discovered: List[DiscoveredResource] = []
        resources_blocks = parsed.get("resource", [])
        if not isinstance(resources_blocks, list):
            resources_blocks = [resources_blocks]

        for block in resources_blocks:
            if not isinstance(block, dict):
                continue

            for raw_res_type, instances in block.items():
                res_type = _clean_value(raw_res_type)
                provider = res_type.split("_")[0] if "_" in res_type else "unknown"
                category = RESOURCE_CATEGORY_MAP.get(res_type, ResourceCategory.OTHER)

                if not isinstance(instances, dict):
                    continue

                for raw_name, raw_config in instances.items():
                    name = _clean_value(raw_name)
                    cleaned_config = _clean_value(raw_config) if isinstance(raw_config, dict) else {}

                    known_attrs, unknown_attrs = _separate_known_and_unknown(cleaned_config)

                    res = DiscoveredResource(
                        resource_id=f"res-{provider}-{res_type}.{name}",
                        resource_type=res_type,
                        provider=provider,
                        name=name,
                        category=category,
                        source_file=source_file,
                        source_location=f"resource \"{res_type}\" \"{name}\"",
                        configuration=cleaned_config,
                        attributes_known=known_attrs,
                        attributes_unknown=unknown_attrs,
                    )
                    discovered.append(res)

        return discovered

    def parse_file(self, file_path: Path, workspace_root: Path) -> List[DiscoveredResource]:
        """Read and parse a single .tf file relative to workspace root."""
        rel_path = str(file_path.relative_to(workspace_root)).replace("\\", "/")
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            return self.parse_hcl_content(content=content, source_file=rel_path)
        except Exception as err:
            logger.error("Error reading Terraform file '%s': %s", rel_path, err)
            return []
