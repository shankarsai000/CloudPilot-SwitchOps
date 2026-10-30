"""
CloudPilot SwitchOps — Docker Compose Safe YAML Parser

Parses Docker Compose configuration files (docker-compose.yml / compose.yaml)
using PyYAML safe_load. Extracts service declarations, network bindings,
volume mounts, healthchecks, restart policies, and resource limits, while
strictly redacting sensitive environment variables.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.core.logging import redact_secrets
from app.domain.inventory import DiscoveredResource, ResourceCategory

logger = logging.getLogger("cloudpilot.discovery.compose")

# Keys whose environment values must always be sanitized
SENSITIVE_ENV_KEYS = re.compile(
    r"(pass|pwd|secret|token|key|cred|auth|cert)", re.IGNORECASE
)


def _sanitize_environment(env_config: Any) -> Dict[str, str]:
    """Sanitize environment variables dictionary or list, masking sensitive credentials."""
    sanitized: Dict[str, str] = {}
    if isinstance(env_config, dict):
        for k, v in env_config.items():
            str_key = str(k)
            str_val = str(v) if v is not None else ""
            if SENSITIVE_ENV_KEYS.search(str_key):
                sanitized[str_key] = "[REDACTED]"
            else:
                sanitized[str_key] = redact_secrets(str_val)
    elif isinstance(env_config, list):
        for item in env_config:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                if SENSITIVE_ENV_KEYS.search(k):
                    sanitized[k] = "[REDACTED]"
                else:
                    sanitized[k] = redact_secrets(v)
            elif isinstance(item, str):
                sanitized[item] = "[REDACTED]"
    return sanitized


def _parse_port_binding(port_entry: Any) -> Dict[str, Any]:
    """
    Parse a Docker compose port entry into normalized binding attributes.
    Supports formats:
      - "80:80"
      - "0.0.0.0:8080:80"
      - "127.0.0.1:5432:5432"
      - 8000
    """
    raw_str = str(port_entry).strip()
    result = {
        "raw": raw_str,
        "host_ip": "0.0.0.0",
        "host_port": None,
        "container_port": None,
        "is_publicly_bound": False,
    }

    parts = raw_str.split(":")
    if len(parts) == 1:
        # Just container port or host:container implicit
        try:
            result["container_port"] = int(parts[0])
        except ValueError:
            pass
    elif len(parts) == 2:
        # host_port:container_port
        try:
            result["host_port"] = int(parts[0])
            result["container_port"] = int(parts[1].split("/")[0])
            result["host_ip"] = "0.0.0.0"
            result["is_publicly_bound"] = True
        except ValueError:
            pass
    elif len(parts) == 3:
        # host_ip:host_port:container_port
        result["host_ip"] = parts[0]
        try:
            result["host_port"] = int(parts[1])
            result["container_port"] = int(parts[2].split("/")[0])
        except ValueError:
            pass
        if result["host_ip"] in ("0.0.0.0", "::", ""):
            result["is_publicly_bound"] = True

    result["target"] = result["container_port"]
    return result


class ComposeParser:
    """Parses Docker Compose YAML files safely into DiscoveredResource models."""

    def parse_compose_content(self, content: str, source_file: str) -> List[DiscoveredResource]:
        """Parse raw YAML string using safe_load and extract services."""
        if not content.strip():
            return []

        try:
            data = yaml.safe_load(content)
        except Exception as exc:
            logger.warning("Failed to parse YAML in '%s': %s", source_file, exc)
            return []

        if not isinstance(data, dict):
            return []

        services = data.get("services", {})
        if not isinstance(services, dict):
            return []

        discovered: List[DiscoveredResource] = []

        for service_name, s_cfg in services.items():
            if not isinstance(s_cfg, dict):
                continue

            image = s_cfg.get("image", "unknown")
            raw_ports = s_cfg.get("ports", [])
            parsed_ports = [_parse_port_binding(p) for p in raw_ports] if isinstance(raw_ports, list) else []

            volumes = s_cfg.get("volumes", [])
            sanitized_env = _sanitize_environment(s_cfg.get("environment", {}))
            healthcheck = s_cfg.get("healthcheck")
            restart_policy = s_cfg.get("restart")
            privileged = bool(s_cfg.get("privileged", False))
            network_mode = s_cfg.get("network_mode")

            # Deploy / resource limits
            deploy_cfg = s_cfg.get("deploy", {})
            resources_cfg = deploy_cfg.get("resources", {}) if isinstance(deploy_cfg, dict) else {}
            limits = resources_cfg.get("limits", {}) if isinstance(resources_cfg, dict) else {}
            replicas = deploy_cfg.get("replicas", 1) if isinstance(deploy_cfg, dict) else 1

            # Categorize service
            lower_img = str(image).lower()
            if any(db in lower_img for db in ("postgres", "mysql", "redis", "mongo", "mariadb", "cassandra")):
                category = ResourceCategory.DATABASE
            else:
                category = ResourceCategory.CONTAINER

            known_attrs: Dict[str, Any] = {
                "service_name": service_name,
                "image": image,
                "ports": parsed_ports,
                "volumes": volumes,
                "environment": sanitized_env,
                "healthcheck": healthcheck,
                "restart_policy": restart_policy,
                "privileged": privileged,
                "network_mode": network_mode,
                "resource_limits": limits,
                "replicas": replicas,
            }

            # Check unknown attributes
            unknown_attrs: List[str] = []
            if isinstance(image, str) and "${" in image:
                unknown_attrs.append("image")

            res = DiscoveredResource(
                resource_id=f"res-docker-compose_service.{service_name}",
                resource_type="compose_service",
                provider="docker",
                name=service_name,
                category=category,
                source_file=source_file,
                source_location=f"services.{service_name}",
                configuration=known_attrs,
                attributes_known=known_attrs,
                attributes_unknown=unknown_attrs,
            )
            discovered.append(res)

        return discovered

    def parse_file(self, file_path: Path, workspace_root: Path) -> List[DiscoveredResource]:
        """Read and parse a Docker Compose file safely."""
        rel_path = str(file_path.relative_to(workspace_root)).replace("\\", "/")
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            return self.parse_compose_content(content=content, source_file=rel_path)
        except Exception as err:
            logger.error("Error reading Docker Compose file '%s': %s", rel_path, err)
            return []
