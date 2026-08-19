"""
Deployment Analyzer — Deployment intelligence and DORA metrics.

Tracks deployment frequency, history, failure rates, rollback history,
and deployment strategies. Calculates DORA metrics for application
health assessment.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from models_application import (
    Application,
    DeploymentRecord,
    DeploymentStatus,
    DeploymentStrategy,
)
from models_resource import CloudResource

logger = logging.getLogger(__name__)


class DORAMetrics:
    """DORA (DevOps Research and Assessment) performance metrics."""

    def __init__(
        self,
        deployment_frequency: float,
        lead_time_hours: float,
        change_failure_rate: float,
        mean_time_to_recovery_hours: float,
    ) -> None:
        """Initialize DORA metrics.

        Args:
            deployment_frequency: Deployments per day
            lead_time_hours: Average lead time for changes in hours
            change_failure_rate: Fraction of deployments causing failures (0.0-1.0)
            mean_time_to_recovery_hours: Average recovery time in hours
        """
        self.deployment_frequency: float = deployment_frequency
        self.lead_time_hours: float = lead_time_hours
        self.change_failure_rate: float = change_failure_rate
        self.mean_time_to_recovery_hours: float = mean_time_to_recovery_hours

    @property
    def performance_level(self) -> str:
        """Classify DORA performance level.

        Returns:
            Performance level: elite, high, medium, low
        """
        if (
            self.deployment_frequency >= 1.0
            and self.lead_time_hours <= 24
            and self.change_failure_rate <= 0.05
            and self.mean_time_to_recovery_hours <= 1
        ):
            return "elite"
        if (
            self.deployment_frequency >= 0.14  # weekly
            and self.lead_time_hours <= 168  # 1 week
            and self.change_failure_rate <= 0.15
            and self.mean_time_to_recovery_hours <= 24
        ):
            return "high"
        if (
            self.deployment_frequency >= 0.033  # monthly
            and self.change_failure_rate <= 0.30
        ):
            return "medium"
        return "low"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dict representation
        """
        return {
            "deployment_frequency_per_day": round(self.deployment_frequency, 4),
            "lead_time_hours": round(self.lead_time_hours, 1),
            "change_failure_rate": round(self.change_failure_rate, 4),
            "mean_time_to_recovery_hours": round(self.mean_time_to_recovery_hours, 1),
            "performance_level": self.performance_level,
        }


class DeploymentAnalyzer:
    """Analyzes deployment patterns, history, and performance metrics.

    Processes deployment records to calculate DORA metrics,
    detect deployment strategies, and identify deployment health trends.
    """

    def __init__(self) -> None:
        """Initialize deployment analyzer."""
        self._deployment_store: dict[str, list[DeploymentRecord]] = {}
        logger.info("DeploymentAnalyzer initialized")

    def analyze_deployments(
        self,
        applications: list[Application],
        resources: Optional[list[CloudResource]] = None,
    ) -> dict[str, list[DeploymentRecord]]:
        """Analyze deployments for all applications.

        Synthesizes deployment records from resource metadata
        (container image tags, launch configs, etc.).

        Args:
            applications: Discovered applications
            resources: M1 cloud resources for metadata extraction

        Returns:
            Dict mapping application_id → deployment records
        """
        resource_map: dict[str, CloudResource] = {}
        if resources:
            resource_map = {r.id: r for r in resources}

        for app in applications:
            records = self._extract_deployments(app, resource_map)
            self._deployment_store[app.application_id] = records
            app.deployments = records

        total = sum(len(r) for r in self._deployment_store.values())
        logger.info(
            "Deployment analysis complete: %d deployments across %d applications",
            total,
            len(self._deployment_store),
        )
        return self._deployment_store

    def get_deployment_history(
        self,
        application_id: str,
        limit: int = 50,
    ) -> list[DeploymentRecord]:
        """Get chronological deployment history for an application.

        Args:
            application_id: Application identifier
            limit: Maximum records to return

        Returns:
            Deployment records sorted by timestamp (newest first)
        """
        records = self._deployment_store.get(application_id, [])
        sorted_records = sorted(
            records, key=lambda r: r.deployed_at, reverse=True
        )
        return sorted_records[:limit]

    def calculate_dora_metrics(
        self,
        application_id: str,
        window_days: int = 30,
    ) -> DORAMetrics:
        """Calculate DORA metrics for an application.

        Args:
            application_id: Application identifier
            window_days: Analysis window in days

        Returns:
            DORAMetrics instance
        """
        records = self._deployment_store.get(application_id, [])
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        recent = [r for r in records if r.deployed_at >= cutoff]

        # Deployment frequency (per day)
        frequency = len(recent) / window_days if window_days > 0 else 0.0

        # Lead time (average deployment duration)
        durations = [
            r.duration_seconds
            for r in recent
            if r.duration_seconds is not None and r.duration_seconds > 0
        ]
        avg_lead_time_hours = (
            (sum(durations) / len(durations) / 3600) if durations else 0.0
        )

        # Change failure rate
        total_deploys = len(recent)
        failed = sum(
            1
            for r in recent
            if r.status in (DeploymentStatus.FAILED, DeploymentStatus.ROLLED_BACK)
        )
        failure_rate = failed / total_deploys if total_deploys > 0 else 0.0

        # Mean time to recovery
        recovery_times: list[float] = []
        sorted_recent = sorted(recent, key=lambda r: r.deployed_at)
        for i, record in enumerate(sorted_recent):
            if record.status == DeploymentStatus.FAILED:
                # Find next successful deployment
                for j in range(i + 1, len(sorted_recent)):
                    if sorted_recent[j].status == DeploymentStatus.SUCCESS:
                        recovery_delta = (
                            sorted_recent[j].deployed_at - record.deployed_at
                        )
                        recovery_times.append(
                            recovery_delta.total_seconds() / 3600
                        )
                        break

        mttr = (
            sum(recovery_times) / len(recovery_times) if recovery_times else 0.0
        )

        return DORAMetrics(
            deployment_frequency=frequency,
            lead_time_hours=avg_lead_time_hours,
            change_failure_rate=failure_rate,
            mean_time_to_recovery_hours=mttr,
        )

    def get_deployment_stats(
        self, application_id: str
    ) -> dict[str, Any]:
        """Get deployment statistics summary.

        Args:
            application_id: Application identifier

        Returns:
            Statistics dict
        """
        records = self._deployment_store.get(application_id, [])
        if not records:
            return {
                "total_deployments": 0,
                "success_rate": 0.0,
                "rollback_count": 0,
                "strategies_used": [],
                "dora_metrics": DORAMetrics(0, 0, 0, 0).to_dict(),
            }

        total = len(records)
        successful = sum(1 for r in records if r.status == DeploymentStatus.SUCCESS)
        rollbacks = sum(1 for r in records if r.is_rollback)
        strategies = list({r.strategy.value for r in records})

        dora = self.calculate_dora_metrics(application_id)

        return {
            "total_deployments": total,
            "success_rate": round(successful / total, 3) if total > 0 else 0.0,
            "rollback_count": rollbacks,
            "strategies_used": strategies,
            "most_recent": records[-1].deployed_at.isoformat() if records else None,
            "dora_metrics": dora.to_dict(),
        }

    def _extract_deployments(
        self,
        app: Application,
        resource_map: dict[str, CloudResource],
    ) -> list[DeploymentRecord]:
        """Extract deployment records from resource metadata.

        Looks for deployment indicators in resource metadata:
        - Container image tags (K8s deployments)
        - Launch configuration versions (EC2/ASG)
        - Function versions (Lambda)
        - Deployment annotations

        Args:
            app: Application
            resource_map: Resource ID → CloudResource mapping

        Returns:
            List of DeploymentRecord objects
        """
        records: list[DeploymentRecord] = []

        for resource_id in app.resource_ids:
            resource = resource_map.get(resource_id)
            if not resource:
                continue

            # Extract from deployment metadata
            deploy_history = resource.metadata.get("deployment_history", [])
            if isinstance(deploy_history, list):
                for entry in deploy_history:
                    if isinstance(entry, dict):
                        record = self._parse_deployment_entry(
                            app.application_id, entry
                        )
                        if record:
                            records.append(record)

            # Extract current version as a deployment record
            version = resource.metadata.get("version") or resource.metadata.get(
                "image_tag"
            ) or resource.metadata.get("function_version")
            if version:
                strategy = self._detect_strategy(resource)
                record = DeploymentRecord(
                    deployment_id=f"deploy-{uuid.uuid4().hex[:12]}",
                    application_id=app.application_id,
                    version=str(version),
                    strategy=strategy,
                    status=DeploymentStatus.SUCCESS,
                    deployed_at=resource.updated_at,
                    deployed_by=resource.metadata.get("deployed_by", "unknown"),
                    commit_sha=resource.metadata.get("commit_sha"),
                    metadata={"source": "resource_metadata", "resource_id": resource_id},
                )
                records.append(record)

        # Deduplicate by version
        seen_versions: set[str] = set()
        unique: list[DeploymentRecord] = []
        for record in records:
            if record.version not in seen_versions:
                seen_versions.add(record.version)
                unique.append(record)

        return sorted(unique, key=lambda r: r.deployed_at)

    @staticmethod
    def _parse_deployment_entry(
        application_id: str, entry: dict[str, Any]
    ) -> Optional[DeploymentRecord]:
        """Parse a deployment entry from resource metadata.

        Args:
            application_id: Parent application ID
            entry: Deployment metadata dict

        Returns:
            DeploymentRecord or None if unparseable
        """
        version = entry.get("version") or entry.get("revision")
        if not version:
            return None

        deployed_at_str = entry.get("deployed_at") or entry.get("timestamp")
        try:
            deployed_at = (
                datetime.fromisoformat(deployed_at_str)
                if deployed_at_str
                else datetime.utcnow()
            )
        except (ValueError, TypeError):
            deployed_at = datetime.utcnow()

        status_str = entry.get("status", "success").lower()
        status_map = {
            "success": DeploymentStatus.SUCCESS,
            "failed": DeploymentStatus.FAILED,
            "rolled_back": DeploymentStatus.ROLLED_BACK,
            "in_progress": DeploymentStatus.IN_PROGRESS,
            "cancelled": DeploymentStatus.CANCELLED,
        }
        status = status_map.get(status_str, DeploymentStatus.SUCCESS)

        strategy_str = entry.get("strategy", "unknown").lower()
        strategy_map = {
            "rolling": DeploymentStrategy.ROLLING,
            "blue_green": DeploymentStrategy.BLUE_GREEN,
            "canary": DeploymentStrategy.CANARY,
            "recreate": DeploymentStrategy.RECREATE,
        }
        strategy = strategy_map.get(strategy_str, DeploymentStrategy.UNKNOWN)

        return DeploymentRecord(
            deployment_id=f"deploy-{uuid.uuid4().hex[:12]}",
            application_id=application_id,
            version=str(version),
            strategy=strategy,
            status=status,
            deployed_at=deployed_at,
            duration_seconds=entry.get("duration_seconds"),
            deployed_by=entry.get("deployed_by"),
            commit_sha=entry.get("commit_sha"),
            is_rollback=entry.get("is_rollback", False),
            change_summary=entry.get("change_summary"),
            metadata={"source": "deployment_history"},
        )

    @staticmethod
    def _detect_strategy(resource: CloudResource) -> DeploymentStrategy:
        """Detect deployment strategy from resource metadata.

        Args:
            resource: Cloud resource

        Returns:
            Detected DeploymentStrategy
        """
        metadata = resource.metadata

        # K8s strategy detection
        strategy = metadata.get("strategy", {})
        if isinstance(strategy, dict):
            strategy_type = strategy.get("type", "").lower()
            if strategy_type == "rollingupdate":
                return DeploymentStrategy.ROLLING
            if strategy_type == "recreate":
                return DeploymentStrategy.RECREATE

        # Check for canary/blue-green indicators
        if metadata.get("canary_enabled") or metadata.get("canary_weight"):
            return DeploymentStrategy.CANARY
        if metadata.get("blue_green") or metadata.get("active_color"):
            return DeploymentStrategy.BLUE_GREEN

        # Tag-based detection
        tags = resource.tags
        deploy_strategy = tags.get("deploy-strategy", "").lower()
        if "canary" in deploy_strategy:
            return DeploymentStrategy.CANARY
        if "blue" in deploy_strategy or "green" in deploy_strategy:
            return DeploymentStrategy.BLUE_GREEN
        if "rolling" in deploy_strategy:
            return DeploymentStrategy.ROLLING

        return DeploymentStrategy.UNKNOWN
