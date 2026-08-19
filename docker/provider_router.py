"""
Provider Router Component

Routes plans to target executors (AWS, Azure, GCP, Kubernetes, Terraform, Ansible)
based on the plan's provider metadata.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from aws_executor import AWSExecutor
from azure_executor import AzureExecutor
from gcp_executor import GCPExecutor
from kubernetes_executor import KubernetesExecutor
from terraform_executor import TerraformExecutor
from ansible_executor import AnsibleExecutor

logger = logging.getLogger(__name__)


class ProviderRouter:
    """Routes execution commands to the matching provider executor adapter."""

    def __init__(
        self,
        aws: Optional[AWSExecutor] = None,
        azure: Optional[AzureExecutor] = None,
        gcp: Optional[GCPExecutor] = None,
        k8s: Optional[KubernetesExecutor] = None,
        terraform: Optional[TerraformExecutor] = None,
        ansible: Optional[AnsibleExecutor] = None,
    ) -> None:
        """Initialize Provider Router with adapter instances."""
        self.aws = aws or AWSExecutor()
        self.azure = azure or AzureExecutor()
        self.gcp = gcp or GCPExecutor()
        self.k8s = k8s or KubernetesExecutor()
        self.terraform = terraform or TerraformExecutor()
        self.ansible = ansible or AnsibleExecutor()

    def get_executor(self, plan: dict[str, Any]) -> Any:
        """Get the executor instance corresponding to the provider.

        Args:
            plan: Change plan specifications containing provider metadata

        Returns:
            Executor adapter instance
        """
        # Read from plan provider or fallback to target-based heuristics
        prov = str(plan.get("provider", "")).upper()
        if not prov:
            target = str(plan.get("target_id", "")).lower()
            if "ec2" in target or "rds" in target or "aws" in target:
                prov = "AWS"
            elif "azure" in target or "vm" in target:
                prov = "AZURE"
            elif "gcp" in target or "gce" in target:
                prov = "GCP"
            elif "k8s" in target or "pod" in target or "helm" in target:
                prov = "KUBERNETES"
            elif "tf" in target or "state" in target:
                prov = "TERRAFORM"
            elif "ansible" in target or "host" in target:
                prov = "ANSIBLE"
            else:
                prov = "AWS"  # Default fallback

        if prov == "AZURE":
            return self.azure
        elif prov == "GCP":
            return self.gcp
        elif prov == "KUBERNETES":
            return self.k8s
        elif prov == "TERRAFORM":
            return self.terraform
        elif prov == "ANSIBLE":
            return self.ansible
        else:
            return self.aws

    def execute(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Route execute command to the matching provider executor."""
        executor = self.get_executor(plan)
        return executor.execute(plan)

    def rollback(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Route rollback command to the matching provider executor."""
        executor = self.get_executor(plan)
        return executor.rollback(plan)

    def validate(self, plan: dict[str, Any]) -> bool:
        """Route validate command to the matching provider executor."""
        executor = self.get_executor(plan)
        return executor.validate(plan)

    def monitor(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Route monitor command to the matching provider executor."""
        executor = self.get_executor(plan)
        return executor.monitor(plan)
