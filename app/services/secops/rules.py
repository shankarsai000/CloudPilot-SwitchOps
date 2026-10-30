"""
CloudPilot SwitchOps — Security and Reliability Deterministic Rule Catalog

Implements reproducible, evidence-based policy checkers for cloud and container resources.
Each rule returns a Finding domain object when a vulnerability or reliability deficit is detected.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.domain.finding import Finding, FindingCategory, FindingSeverity
from app.domain.inventory import DiscoveredResource, InfrastructureInventory

# Sensitive ports requiring restricted access
SENSITIVE_MANAGEMENT_PORTS = {22, 3389}
SENSITIVE_DATABASE_PORTS = {5432, 3306, 1433, 27017, 6379, 11211, 9200}
ALL_SENSITIVE_PORTS = SENSITIVE_MANAGEMENT_PORTS | SENSITIVE_DATABASE_PORTS


def evaluate_sec_001_redis_exposure(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """SEC-001: Redis bound to public interface or lacking authentication."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    image = str(known.get("image", "")).lower()
    name = resource.name.lower()

    if "redis" not in image and "redis" not in name:
        return None

    ports = known.get("ports", [])
    exposed_publicly = False
    port_evidence = []

    for p in ports:
        if isinstance(p, dict):
            target = p.get("target") or p.get("container_port") or p.get("host_port")
            host_ip = p.get("host_ip", "")
            if target == 6379:
                if host_ip in ("0.0.0.0", "", "::", "*") or p.get("is_publicly_bound", False):
                    exposed_publicly = True
                    port_evidence.append(p)
        elif isinstance(p, str) and "6379" in p:
            if p.startswith("6379") or "0.0.0.0:6379" in p:
                exposed_publicly = True
                port_evidence.append(p)

    if exposed_publicly:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-001",
            severity=FindingSeverity.HIGH,
            title=f"Redis service '{resource.name}' publicly exposed on port 6379",
            description=(
                f"Redis service '{resource.name}' binds port 6379 to 0.0.0.0 without network isolation. "
                f"Unauthenticated or exposed Redis instances are vulnerable to remote code execution and unauthorized data exfiltration."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value=port_evidence,
            expected_value="Internal container network binding only (e.g. 127.0.0.1:6379 or expose without host port)",
            evidence={"ports": port_evidence, "image": image, "service": resource.name},
            recommendation="Bind Redis exclusively to 127.0.0.1 or communicate over Docker bridge network without host port publishing.",
            confidence=0.98,
        )
    return None


def evaluate_sec_002_database_exposure(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """SEC-002: Relational or NoSQL database port directly exposed to public host."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    image = str(known.get("image", "")).lower()
    name = resource.name.lower()

    is_db_image = any(db_kw in image or db_kw in name for db_kw in ["postgres", "mysql", "mariadb", "mongo", "cassandra"])
    if not is_db_image:
        return None

    ports = known.get("ports", [])
    exposed_ports = []

    for p in ports:
        if isinstance(p, dict):
            target = p.get("target") or p.get("container_port") or p.get("host_port")
            host_ip = p.get("host_ip", "")
            if target in SENSITIVE_DATABASE_PORTS:
                if host_ip in ("0.0.0.0", "", "::", "*") or p.get("is_publicly_bound", False):
                    exposed_ports.append(p)
        elif isinstance(p, str):
            for sp in SENSITIVE_DATABASE_PORTS:
                if str(sp) in p and (p.startswith(str(sp)) or f"0.0.0.0:{sp}" in p):
                    exposed_ports.append(p)

    if exposed_ports:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-002",
            severity=FindingSeverity.HIGH,
            title=f"Database service '{resource.name}' exposed on public host interface",
            description=(
                f"Database container '{resource.name}' exposes database listener port on public interface. "
                f"Exposing database engines directly to host networking bypasses perimeter firewalls and invites brute-force attacks."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value=exposed_ports,
            expected_value="Database reachable only via internal overlay network, no host port mapped to 0.0.0.0",
            evidence={"exposed_ports": exposed_ports, "service": resource.name},
            recommendation="Remove public host port binding from database container; access via application network or bastion.",
            confidence=0.95,
        )
    return None


def evaluate_sec_003_unrestricted_ingress(
    resource: DiscoveredResource,
    task_id: str,
) -> List[Finding]:
    """SEC-003: Security group allowing unrestricted ingress 0.0.0.0/0 on sensitive ports."""
    findings = []
    if resource.resource_type != "aws_security_group":
        return findings

    known = resource.attributes_known
    raw_ingress = known.get("ingress", [])

    # Ingress could be a list of blocks or a single block
    ingress_rules = raw_ingress if isinstance(raw_ingress, list) else [raw_ingress]

    for rule in ingress_rules:
        if not isinstance(rule, dict):
            continue
        cidr_blocks = rule.get("cidr_blocks", [])
        if isinstance(cidr_blocks, str):
            cidr_blocks = [cidr_blocks]

        if "0.0.0.0/0" in cidr_blocks:
            from_port = rule.get("from_port")
            to_port = rule.get("to_port")
            try:
                fp = int(from_port) if from_port is not None else 0
                tp = int(to_port) if to_port is not None else 65535
            except (ValueError, TypeError):
                continue

            violating_ports = [p for p in ALL_SENSITIVE_PORTS if fp <= p <= tp]
            if violating_ports:
                severity = FindingSeverity.CRITICAL if (22 in violating_ports or 3389 in violating_ports) else FindingSeverity.HIGH
                findings.append(
                    Finding(
                        task_id=task_id,
                        agent_id="secops-specialist",
                        category=FindingCategory.SECURITY,
                        rule_id="SEC-003",
                        severity=severity,
                        title=f"Unrestricted 0.0.0.0/0 ingress to port(s) {violating_ports} on '{resource.name}'",
                        description=(
                            f"Security group '{resource.name}' allows inbound traffic from 0.0.0.0/0 on sensitive port(s) {violating_ports}. "
                            f"Public access to management (SSH/RDP) or databases significantly increases compromise risk."
                        ),
                        source_file=resource.source_file,
                        source_location=resource.source_location,
                        observed_value=f"cidr_blocks = ['0.0.0.0/0'], ports {fp}-{tp}",
                        expected_value="Specific corporate CIDR or VPN IP gateway",
                        evidence={"violating_ports": violating_ports, "rule": rule, "sg": resource.name},
                        recommendation="Restrict ingress cidr_blocks to verified administrative IPs or use AWS Systems Manager Session Manager.",
                        confidence=0.99,
                    )
                )
    return findings


def evaluate_sec_004_privileged_container(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """SEC-004: Container running with privileged flag enabled."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    privileged = known.get("privileged", False)
    if privileged is True or str(privileged).lower() == "true":
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-004",
            severity=FindingSeverity.CRITICAL,
            title=f"Privileged container execution enabled on '{resource.name}'",
            description=(
                f"Service '{resource.name}' has `privileged: true` set. Privileged containers grant full access "
                f"to all host devices and bypass root namespace separation, enabling trivial container breakouts."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value="privileged: true",
            expected_value="privileged: false (or omitted) with minimal granular capabilities (cap_add)",
            evidence={"privileged": True, "service": resource.name},
            recommendation="Disable `privileged: true` and specify granular Linux capabilities (e.g. NET_ADMIN) only if strictly required.",
            confidence=1.0,
        )
    return None


def evaluate_sec_005_docker_socket_mount(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """SEC-005: Host Docker socket mounted into container."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    volumes = known.get("volumes", [])
    socket_mounted = False
    evidence_vol = ""

    for vol in volumes:
        vol_str = str(vol)
        if "/var/run/docker.sock" in vol_str or "docker.sock" in vol_str:
            socket_mounted = True
            evidence_vol = vol_str
            break

    if socket_mounted:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-005",
            severity=FindingSeverity.CRITICAL,
            title=f"Docker socket mounted into container '{resource.name}'",
            description=(
                f"Service '{resource.name}' mounts `/var/run/docker.sock`. "
                f"Mounting the Docker daemon socket provides root-equivalent control over the host node."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value=evidence_vol,
            expected_value="No host Docker socket mounts in application containers",
            evidence={"mounted_volume": evidence_vol, "service": resource.name},
            recommendation="Remove Docker socket mount and communicate via restricted APIs or dedicated agent workflows.",
            confidence=1.0,
        )
    return None


def evaluate_sec_006_host_network_mode(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """SEC-006: Host network mode configured on container."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    net_mode = str(known.get("network_mode", "")).lower()

    if net_mode == "host":
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-006",
            severity=FindingSeverity.HIGH,
            title=f"Host network mode enabled on service '{resource.name}'",
            description=(
                f"Service '{resource.name}' configures `network_mode: host`. "
                f"Host networking removes container network isolation and exposes host network interfaces directly."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value="network_mode: host",
            expected_value="Default bridge or user-defined bridge network",
            evidence={"network_mode": "host", "service": resource.name},
            recommendation="Switch to a user-defined bridge network and publish only necessary ports.",
            confidence=0.95,
        )
    return None


def evaluate_sec_007_s3_public_access(
    resource: DiscoveredResource,
    all_resources: List[DiscoveredResource],
    task_id: str,
) -> Optional[Finding]:
    """SEC-007: S3 bucket configured with public ACL or lacking public access block."""
    if resource.resource_type not in ("aws_s3_bucket", "aws_s3_bucket_v2"):
        return None

    known = resource.attributes_known
    acl = str(known.get("acl", "")).lower()

    if "public" in acl:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-007",
            severity=FindingSeverity.CRITICAL,
            title=f"S3 bucket '{resource.name}' configured with public ACL '{acl}'",
            description=(
                f"S3 bucket '{resource.name}' defines public ACL (`acl = '{acl}'`). "
                f"This permits unauthenticated internet access to bucket contents."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value=f"acl = '{acl}'",
            expected_value="acl = 'private' with explicit public access block",
            evidence={"acl": acl, "bucket_name": resource.name},
            recommendation="Set bucket ACL to 'private' and configure aws_s3_bucket_public_access_block.",
            confidence=1.0,
        )

    # Check if a corresponding public access block exists
    has_pab = any(
        r.resource_type == "aws_s3_bucket_public_access_block"
        and (resource.name in str(r.attributes_known.get("bucket", "")) or r.name == resource.name)
        for r in all_resources
    )

    if not has_pab:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-007",
            severity=FindingSeverity.MEDIUM,
            title=f"S3 bucket '{resource.name}' missing Public Access Block configuration",
            description=(
                f"S3 bucket '{resource.name}' does not have an associated `aws_s3_bucket_public_access_block` resource. "
                f"Without public access blocks, future policy drifts can inadvertently expose stored assets."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value="Missing aws_s3_bucket_public_access_block",
            expected_value="aws_s3_bucket_public_access_block with block_public_acls=true and block_public_policy=true",
            evidence={"bucket_name": resource.name},
            recommendation="Add `aws_s3_bucket_public_access_block` enforcing all four public access blocks.",
            confidence=0.88,
        )

    return None


def evaluate_sec_008_unencrypted_ebs(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """SEC-008: EBS volume without server-side encryption enabled."""
    if resource.resource_type != "aws_ebs_volume":
        return None

    known = resource.attributes_known
    encrypted = known.get("encrypted")

    if encrypted is False or str(encrypted).lower() == "false" or encrypted is None:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-008",
            severity=FindingSeverity.HIGH,
            title=f"EBS volume '{resource.name}' unencrypted at rest",
            description=(
                f"EBS volume '{resource.name}' has `encrypted` set to false or omitted. "
                f"Storage volumes containing application data should always be encrypted at rest using KMS."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value=f"encrypted = {encrypted}",
            expected_value="encrypted = true with kms_key_id specified",
            evidence={"encrypted": encrypted, "volume_name": resource.name},
            recommendation="Set `encrypted = true` in EBS volume configuration.",
            confidence=0.95,
        )
    return None


def evaluate_sec_009_unencrypted_rds(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """SEC-009: RDS instance without storage encryption enabled."""
    if resource.resource_type not in ("aws_db_instance", "aws_rds_cluster_instance"):
        return None

    known = resource.attributes_known
    storage_encrypted = known.get("storage_encrypted")

    if storage_encrypted is False or str(storage_encrypted).lower() == "false" or storage_encrypted is None:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.SECURITY,
            rule_id="SEC-009",
            severity=FindingSeverity.HIGH,
            title=f"RDS instance '{resource.name}' lacks storage encryption",
            description=(
                f"RDS database instance '{resource.name}' does not enforce storage encryption at rest. "
                f"Unencrypted relational databases violate standard compliance benchmarks (SOC2, HIPAA, PCI-DSS)."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value=f"storage_encrypted = {storage_encrypted}",
            expected_value="storage_encrypted = true",
            evidence={"storage_encrypted": storage_encrypted, "db_name": resource.name},
            recommendation="Enable `storage_encrypted = true` on the RDS instance definition.",
            confidence=0.95,
        )
    return None


def evaluate_sec_010_plaintext_credentials(
    resource: DiscoveredResource,
    task_id: str,
) -> List[Finding]:
    """SEC-010: Plain-text sensitive credential or password detected in configuration."""
    findings = []
    known = resource.attributes_known

    # In Terraform: password, master_password, secret_key
    for key, val in known.items():
        if any(secret_kw in key.lower() for secret_kw in ["password", "secret", "private_key", "api_key", "auth_token"]):
            val_str = str(val)
            if val_str and val_str != "[REDACTED]" and not val_str.startswith("${"):
                findings.append(
                    Finding(
                        task_id=task_id,
                        agent_id="secops-specialist",
                        category=FindingCategory.SECURITY,
                        rule_id="SEC-010",
                        severity=FindingSeverity.CRITICAL,
                        title=f"Hardcoded sensitive secret attribute '{key}' in resource '{resource.name}'",
                        description=(
                            f"Resource '{resource.name}' includes plain-text credential attribute '{key}'. "
                            f"Committing credentials to infrastructure-as-code exposes secrets to unauthorized readers and version control."
                        ),
                        source_file=resource.source_file,
                        source_location=resource.source_location,
                        observed_value="[REDACTED_SENSITIVE_STRING]",
                        expected_value="Secret referenced via AWS Secrets Manager, SSM Parameter Store, or environment file",
                        evidence={"attribute_key": key, "resource": resource.name},
                        recommendation=f"Replace static '{key}' with Secrets Manager reference or dynamic lookup.",
                        confidence=0.99,
                    )
                )

    # In Docker Compose: check environment variables that were flagged as sensitive
    if resource.resource_type == "compose_service":
        env = known.get("environment", {})
        if isinstance(env, dict):
            for env_k, env_v in env.items():
                if any(secret_kw in env_k.lower() for secret_kw in ["password", "secret", "token", "auth"]):
                    # Note: parser redacts plain values to [REDACTED], so if it's [REDACTED], a plain secret was detected
                    if env_v == "[REDACTED]":
                        findings.append(
                            Finding(
                                task_id=task_id,
                                agent_id="secops-specialist",
                                category=FindingCategory.SECURITY,
                                rule_id="SEC-010",
                                severity=FindingSeverity.HIGH,
                                title=f"Inline sensitive credential variable '{env_k}' in Compose service '{resource.name}'",
                                description=(
                                    f"Docker Compose service '{resource.name}' specifies sensitive environment variable '{env_k}' "
                                    f"directly in compose declaration instead of loading from external vault or secure env."
                                ),
                                source_file=resource.source_file,
                                source_location=resource.source_location,
                                observed_value=f"{env_k}=[REDACTED]",
                                expected_value="Injected securely at runtime via secrets or docker secrets",
                                evidence={"variable_name": env_k, "service": resource.name},
                                recommendation="Move plain secrets from docker-compose.yml to external secret store or Docker secrets.",
                                confidence=0.92,
                            )
                        )

    return findings


# =========================================================================
# Reliability & SRE Rules
# =========================================================================

def evaluate_rel_001_missing_healthcheck(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """REL-001: Container service missing healthcheck definition."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    has_hc = known.get("has_healthcheck", False)

    if not has_hc:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.RELIABILITY,
            rule_id="REL-001",
            severity=FindingSeverity.MEDIUM,
            title=f"Missing container healthcheck on service '{resource.name}'",
            description=(
                f"Service '{resource.name}' does not declare a healthcheck test. "
                f"Without healthchecks, orchestrators cannot detect unresponsive processes or zombie containers, "
                f"leading to routing traffic to dead services."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value="healthcheck is undefined",
            expected_value="Explicit healthcheck block with test, interval, timeout, and retries",
            evidence={"service": resource.name, "image": known.get("image", "unknown")},
            recommendation="Add `healthcheck` block with appropriate liveness probe command.",
            confidence=0.95,
        )
    return None


def evaluate_rel_002_missing_restart_policy(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """REL-002: Service missing robust restart policy."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    restart = str(known.get("restart", "")).lower()

    if restart not in ("always", "unless-stopped"):
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.RELIABILITY,
            rule_id="REL-002",
            severity=FindingSeverity.LOW,
            title=f"Suboptimal or absent restart policy on service '{resource.name}'",
            description=(
                f"Service '{resource.name}' has restart policy '{restart or 'none'}'. "
                f"If the container crashes or the host reboots, the service will not automatically recover."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value=f"restart: {restart or 'none'}",
            expected_value="restart: 'unless-stopped' or 'always'",
            evidence={"restart_policy": restart, "service": resource.name},
            recommendation="Configure `restart: unless-stopped` to ensure autonomous container recovery.",
            confidence=0.90,
        )
    return None


def evaluate_rel_003_single_point_of_failure(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """REL-003: Single-instance database / SPOF."""
    rtype = resource.resource_type.lower()
    known = resource.attributes_known

    if rtype in ("aws_db_instance", "aws_rds_cluster_instance"):
        multi_az = known.get("multi_az", False)
        if multi_az is False or str(multi_az).lower() == "false":
            return Finding(
                task_id=task_id,
                agent_id="secops-specialist",
                category=FindingCategory.RELIABILITY,
                rule_id="REL-003",
                severity=FindingSeverity.MEDIUM,
                title=f"Single-AZ deployment without failover for RDS '{resource.name}'",
                description=(
                    f"RDS instance '{resource.name}' does not enable Multi-AZ deployment. "
                    f"An availability zone outage or host failure will cause extended downtime until manual intervention."
                ),
                source_file=resource.source_file,
                source_location=resource.source_location,
                observed_value="multi_az: false",
                expected_value="multi_az: true (for high availability production/staging)",
                evidence={"multi_az": False, "db_name": resource.name},
                recommendation="Enable `multi_az = true` or deploy read-replica failover pairing.",
                confidence=0.88,
            )
    return None


def evaluate_rel_004_missing_resource_limits(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """REL-004: Missing resource constraints causing noisy-neighbor risk."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    has_limits = known.get("has_resource_limits", False)

    if not has_limits:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.RELIABILITY,
            rule_id="REL-004",
            severity=FindingSeverity.LOW,
            title=f"Noisy neighbor risk: missing CPU/memory limits on '{resource.name}'",
            description=(
                f"Service '{resource.name}' has no CPU/memory constraints. "
                f"A runaway process or memory leak can starve critical co-located services and crash the host daemon."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value="deploy.resources.limits is undefined",
            expected_value="Bounded CPU and memory limits (e.g. 1.0 CPU, 512MB RAM)",
            evidence={"service": resource.name},
            recommendation="Define `deploy.resources.limits` to contain memory usage.",
            confidence=0.90,
        )
    return None


def evaluate_rel_005_stateful_database_missing_volume(
    resource: DiscoveredResource,
    task_id: str,
) -> Optional[Finding]:
    """REL-005: Stateful database container without persistent volume storage."""
    if resource.resource_type != "compose_service":
        return None

    known = resource.attributes_known
    image = str(known.get("image", "")).lower()
    name = resource.name.lower()

    is_stateful = any(db_kw in image or db_kw in name for db_kw in ["postgres", "mysql", "mariadb", "mongo", "redis"])
    if not is_stateful:
        return None

    volumes = known.get("volumes", [])
    if not volumes:
        return Finding(
            task_id=task_id,
            agent_id="secops-specialist",
            category=FindingCategory.RELIABILITY,
            rule_id="REL-005",
            severity=FindingSeverity.HIGH,
            title=f"Stateful service '{resource.name}' lacks persistent volume storage",
            description=(
                f"Stateful container '{resource.name}' does not configure volume mounts. "
                f"Any container recreation or update will irrevocably destroy all internal state and data."
            ),
            source_file=resource.source_file,
            source_location=resource.source_location,
            observed_value="volumes is empty",
            expected_value="Named volume or persistent host directory mount",
            evidence={"service": resource.name, "image": image},
            recommendation="Attach a persistent Docker named volume to the container data directory.",
            confidence=0.96,
        )
    return None
