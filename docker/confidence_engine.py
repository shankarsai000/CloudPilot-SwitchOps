"""
Confidence Engine Component

Calculates deterministic confidence scores (0-100%) for risk assessments
based on data completeness, topological coverage, historical metadata, and incident counts.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from models_confidence import ConfidenceReport, ConfidenceScore
from models_resource import CloudResource
from models_application import Application

logger = logging.getLogger(__name__)


class ConfidenceEngine:
    """Computes deterministic confidence score metrics based on metadata quality and coverage ratios."""

    def __init__(self) -> None:
        """Initialize Confidence Engine."""
        pass

    def calculate_confidence(
        self,
        target_id: str,
        resource: Optional[CloudResource],
        application: Optional[Application],
        all_resources: list[CloudResource],
        historical_incident_count: int = 0
    ) -> ConfidenceReport:
        """Calculate weighted confidence scores based on available information metrics.

        Formula:
        - Topology Coverage: 30%
        - Historical Incidents: 20%
        - Resource Health: 20%
        - Dependency Accuracy: 20%
        - Business Metadata: 10%

        Args:
            target_id: Target identifier
            resource: Specific CloudResource instance under test
            application: Specific Application instance under test
            all_resources: Context list of all resources
            historical_incident_count: Count of known historic incidents

        Returns:
            ConfidenceReport containing score details and data quality
        """
        # 1. Topology Coverage (30%)
        # Ratio of resources with environment/app tags or mapped inside topology
        tagged_count = sum(1 for r in all_resources if "app" in r.tags or "application" in r.tags)
        topo_coverage_val = (tagged_count / len(all_resources) * 100.0) if all_resources else 100.0
        topo_score = min(topo_coverage_val, 100.0)

        # 2. Historical Incidents (20%)
        # Lower incidents count means higher stability metrics predictability, or more incident history coverage
        # For simplicity, we award higher score if we have clear history record tracing (e.g. at least some records exist, meaning we aren't flying blind)
        # If incident records count is known (or mock history is present), we award 100% minus deduction for extreme outliers
        hist_score = max(100.0 - (historical_incident_count * 10.0), 20.0)

        # 3. Resource Health (20%)
        # Percentage of resources in clean RUNNING or AVAILABLE state
        healthy_count = sum(1 for r in all_resources if r.state.value in ("running", "available"))
        health_score = (healthy_count / len(all_resources) * 100.0) if all_resources else 100.0

        # 4. Dependency Accuracy (20%)
        # Based on whether resources have explicit dependencies or relations defined in metadata
        # Mapped from presence of dependency tags or targets
        rel_count = sum(1 for r in all_resources if r.metadata.get("target_instances") or r.metadata.get("backend_service"))
        dep_score = min((rel_count / len(all_resources) * 300.0), 100.0) if all_resources else 100.0
        if dep_score < 40.0:
            dep_score = 50.0  # default baseline accuracy score

        # 5. Business Metadata (10%)
        # Checked on presence of owner, team, cost tags on target
        biz_score = 0.0
        target_tags = {}
        if resource:
            target_tags = resource.tags
        elif application:
            target_tags = application.tags

        if "owner" in target_tags:
            biz_score += 40.0
        if "team" in target_tags or "team_id" in target_tags:
            biz_score += 40.0
        if "cost_center" in target_tags or "env" in target_tags:
            biz_score += 20.0

        # Final weighted confidence calculation
        final_val = (
            (topo_score * 0.30)
            + (hist_score * 0.20)
            + (health_score * 0.20)
            + (dep_score * 0.20)
            + (biz_score * 0.10)
        )

        quality = "HIGH" if final_val >= 80.0 else "MEDIUM" if final_val >= 50.0 else "LOW"

        score = ConfidenceScore(
            final_score=round(final_val, 2),
            topology_coverage=round(topo_score, 2),
            historical_incidents=round(hist_score, 2),
            resource_health=round(health_score, 2),
            dependency_accuracy=round(dep_score, 2),
            business_metadata=round(biz_score, 2),
        )

        evidence_count = 3
        if resource:
            evidence_count += len(resource.tags)
        if application:
            evidence_count += len(application.tags)

        return ConfidenceReport(
            target_id=target_id,
            score=score,
            evidence_count=evidence_count,
            data_quality_level=quality,
            notes=f"Determined via {quality.lower()} data classification matrix."
        )
