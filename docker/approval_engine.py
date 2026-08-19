"""
Approval Engine Component

Specification Pattern to classify optimization actions into required approval workflows:
- Auto Execute, Approval Required, Executive Approval, Blocked.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from models_strategy import ApprovalLevel
from models_resource import CloudResource
from models_application import Application

logger = logging.getLogger(__name__)


class ApprovalEngine:
    """Classifies risk strategies into administrative approval categories."""

    def __init__(self) -> None:
        """Initialize Approval Engine."""
        pass

    def determine_approval_workflow(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        risk_category: str
    ) -> ApprovalLevel:
        """Determine required approval category using static specifications.

        Args:
            resource: Resource
            application: Application context
            action: Action
            risk_category: qualitative Risk category (SAFE, LOW, MEDIUM, HIGH, CRITICAL)

        Returns:
            ApprovalLevel enum
        """
        # Block production database terminations
        is_db = False
        if resource:
            is_db = resource.type.value in ("rds_database", "rds_cluster", "azure_sql_database", "gcp_sql_instance")
        is_prod = (resource and resource.tags.get("env") == "production") or (application and application.environment.value == "production")

        if is_db and is_prod and action == "TERMINATE":
            return ApprovalLevel.BLOCKED

        # Auto-execute low risk storage/idle cleanup
        is_storage_or_idle = False
        if resource:
            is_storage_or_idle = resource.type.value in ("s3_bucket", "azure_storage_account", "gcp_storage_bucket", "sqs_queue") or "idle" in resource.tags.get("status", "").lower()
        
        if is_storage_or_idle and risk_category in ("SAFE", "LOW"):
            return ApprovalLevel.AUTO_EXECUTE

        # Executive approval for high-risk critical environments
        if risk_category in ("HIGH", "CRITICAL") or (application and application.tier.value == "tier_1"):
            return ApprovalLevel.EXECUTIVE_APPROVAL

        # Default is standard approval required
        return ApprovalLevel.APPROVAL_REQUIRED
