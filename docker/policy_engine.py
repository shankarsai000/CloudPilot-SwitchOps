"""
Policy Engine Component

Specification Pattern implementation for evaluating organization policies and compliance boundaries.
Supports checks on databases, payment service hours, K8s masters, and PCI environments.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from models_resource import CloudResource, ResourceType
from models_application import Application

logger = logging.getLogger(__name__)


class Policy:
    """Represents an organization policy rule."""

    def __init__(
        self,
        policy_id: str,
        name: str,
        description: str,
        severity: str = "CRITICAL",
    ) -> None:
        """Initialize Policy."""
        self.policy_id = policy_id
        self.name = name
        self.description = description
        self.severity = severity

    def is_violated(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        parameters: dict[str, Any],
        is_business_hours: bool
    ) -> bool:
        """Check if policy is violated by the specified action.

        Args:
            resource: CloudResource instance
            application: Application context
            action: Simulated action
            parameters: Action parameters
            is_business_hours: Whether simulated during business hours

        Returns:
            True if policy is violated
        """
        raise NotImplementedError()


class DatabaseTerminationPolicy(Policy):
    """Never terminate production databases."""

    def __init__(self) -> None:
        """Initialize Database Policy."""
        super().__init__(
            policy_id="POL-DB-001",
            name="Prevent Production Database Termination",
            description="Production database instances must never be terminated.",
            severity="CRITICAL"
        )

    def is_violated(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        parameters: dict[str, Any],
        is_business_hours: bool
    ) -> bool:
        """Evaluate database check."""
        if not resource:
            return False

        is_db = resource.type.value in ("rds_database", "rds_cluster", "azure_sql_database", "gcp_sql_instance", "dynamodb_table")
        is_prod = resource.tags.get("env") == "production" or (application and application.environment.value == "production")

        if is_db and is_prod and action == "TERMINATE":
            return True

        return False


class PaymentServiceBusinessHoursPolicy(Policy):
    """Never resize payment services during business hours."""

    def __init__(self) -> None:
        """Initialize Payment hours policy."""
        super().__init__(
            policy_id="POL-PAY-002",
            name="Business Hours Restriction for Payments",
            description="Payment applications and backing services must not be resized or scaled during core business hours.",
            severity="HIGH"
        )

    def is_violated(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        parameters: dict[str, Any],
        is_business_hours: bool
    ) -> bool:
        """Evaluate business hours payment check."""
        if not application:
            return False

        is_payment = "payment" in application.name.lower() or "payment" in application.application_id.lower()
        if is_payment and action == "RESIZE" and is_business_hours:
            return True

        return False


class K8sMasterRestartPolicy(Policy):
    """Never restart Kubernetes masters automatically."""

    def __init__(self) -> None:
        """Initialize K8s master policy."""
        super().__init__(
            policy_id="POL-K8S-003",
            name="Prevent Master Node Direct Restarts",
            description="Kubernetes master and control plane nodes cannot be restarted through automated action sequences.",
            severity="CRITICAL"
        )

    def is_violated(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        parameters: dict[str, Any],
        is_business_hours: bool
    ) -> bool:
        """Evaluate K8s control plane node check."""
        if not resource:
            return False

        # Identify control plane by role tag, master label, or node classifications
        is_k8s = resource.provider == "k8s" or "kubernetes" in resource.name.lower() or "k8s" in resource.name.lower()
        is_master = "master" in resource.name.lower() or resource.tags.get("role") == "master" or resource.metadata.get("role") == "master"

        if is_k8s and is_master and action in ("RESTART", "STOP", "TERMINATE"):
            return True

        return False


class PCIAccessPolicy(Policy):
    """Never modify PCI resources."""

    def __init__(self) -> None:
        """Initialize PCI Policy."""
        super().__init__(
            policy_id="POL-PCI-004",
            name="PCI-DSS Environment Lock",
            description="Resources tagged or identified under PCI compliance scopes cannot be modified or terminated.",
            severity="CRITICAL"
        )

    def is_violated(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        parameters: dict[str, Any],
        is_business_hours: bool
    ) -> bool:
        """Evaluate PCI metadata check."""
        # Check tags or compliance metadata
        is_pci = False
        if resource:
            is_pci = resource.tags.get("compliance") == "pci-dss" or resource.tags.get("PCI") == "true"
        if application and application.criticality:
            is_pci = is_pci or "pci-dss" in application.criticality.compliance_frameworks

        if is_pci and action in ("TERMINATE", "STOP", "RESIZE", "MODIFY_SECURITY_GROUP"):
            return True

        return False


class PolicyEngine:
    """Orchestrates organization policies and evaluates compliance violations."""

    def __init__(self, policies: Optional[list[Policy]] = None) -> None:
        """Initialize Policy Engine."""
        self.policies = policies or [
            DatabaseTerminationPolicy(),
            PaymentServiceBusinessHoursPolicy(),
            K8sMasterRestartPolicy(),
            PCIAccessPolicy()
        ]
        logger.info("PolicyEngine initialized with %d policies", len(self.policies))

    def evaluate_policies(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        parameters: dict[str, Any],
        is_business_hours: bool
    ) -> list[str]:
        """Evaluate actions against policies.

        Args:
            resource: Resource
            application: Application
            action: Action
            parameters: Parameters
            is_business_hours: Business hours status

        Returns:
            List of violation explanations (empty if clean)
        """
        violations = []
        for policy in self.policies:
            try:
                if policy.is_violated(resource, application, action, parameters, is_business_hours):
                    violations.append(f"{policy.policy_id} [{policy.severity}]: {policy.name} - {policy.description}")
            except Exception as e:
                logger.error("Failed to evaluate policy %s: %s", policy.policy_id, e)
        return violations

    def get_configured_policies(self) -> list[dict[str, Any]]:
        """Return details of configured policies.

        Returns:
            List of policy details dicts
        """
        return [
            {
                "policy_id": p.policy_id,
                "name": p.name,
                "description": p.description,
                "severity": p.severity
            }
            for p in self.policies
        ]
