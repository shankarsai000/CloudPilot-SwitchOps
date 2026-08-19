"""
Blast Radius Component

Calculates and constructs the blast radius report and impact propagation graph
for infrastructure actions.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from models_application import Application
from models_impact import BlastRadiusReport, ImpactGraph, ImpactGraphNode, ImpactGraphEdge
from service_graph import ServiceGraph

logger = logging.getLogger(__name__)


class BlastRadiusCalculator:
    """Calculates affected nodes, user counts, and constructs impact representation graphs."""

    def __init__(self) -> None:
        """Initialize Blast Radius Calculator."""
        pass

    def calculate_blast_radius(
        self,
        target_id: str,
        applications: list[Application],
        service_graph: ServiceGraph,
        downstream_data: dict[str, Any],
        cost_correlation_data: dict[str, Any]
    ) -> BlastRadiusReport:
        """Calculate the blast radius report for a resource action.

        Args:
            target_id: Target resource/application ID
            applications: List of applications
            service_graph: Complete service graph
            downstream_data: Downstream analyzer results
            cost_correlation_data: Financial correlation results

        Returns:
            BlastRadiusReport object
        """
        affected_services = downstream_data.get("affected_service_ids", [])
        affected_apps = downstream_data.get("affected_application_ids", [])
        root_service_id = downstream_data.get("root_service_id")

        # Collect affected resource IDs
        affected_resources: set[str] = set()
        if target_id.startswith("res-"):
            affected_resources.add(target_id)
        
        for app in applications:
            if app.application_id in affected_apps:
                for service in app.services:
                    if service.service_id in affected_services:
                        affected_resources.update(service.resource_ids)

        # Collect affected teams
        affected_teams: set[str] = set()
        for app in applications:
            if app.application_id in affected_apps:
                if app.ownership and app.ownership.team:
                    affected_teams.add(app.ownership.team)

        # Estimate affected users count based on application metadata
        users_count = 0
        for app in applications:
            if app.application_id in affected_apps:
                # Add default traffic-based user metrics or static tier mappings
                if app.tier.value == "tier_1":
                    users_count += 5000
                elif app.tier.value == "tier_2":
                    users_count += 1000
                else:
                    users_count += 100

        # Estimate revenue exposure from cost/criticality mappings
        revenue_exposure = 0.0
        for app in applications:
            if app.application_id in affected_apps:
                # Base valuation from monthly cost & tier criticality
                app_cost = app.total_monthly_cost or 0.0
                if app.tier.value == "tier_1":
                    revenue_exposure += app_cost * 1.5
                else:
                    revenue_exposure += app_cost * 0.5

        # Deduce recovery complexity based on size and layers
        depth = downstream_data.get("complexity_depth", 0)
        if depth >= 4 or len(affected_services) >= 6:
            complexity = "COMPLEX"
        elif depth >= 2 or len(affected_services) >= 3:
            complexity = "HIGH"
        elif len(affected_services) >= 1:
            complexity = "MEDIUM"
        else:
            complexity = "LOW"

        # Check SPOF condition
        is_spof = downstream_data.get("complexity_depth", 0) > 0 and len(affected_services) > 1

        return BlastRadiusReport(
            affected_resource_ids=list(affected_resources),
            affected_service_ids=affected_services,
            affected_application_ids=affected_apps,
            affected_teams=list(affected_teams),
            affected_users_count=users_count,
            revenue_exposure_usd=round(revenue_exposure, 2),
            recovery_complexity=complexity,
            has_spof=is_spof
        )

    def build_impact_graph(
        self,
        target_id: str,
        applications: list[Application],
        service_graph: ServiceGraph,
        blast_report: BlastRadiusReport
    ) -> ImpactGraph:
        """Construct the directed ImpactGraph visual representation.

        Args:
            target_id: Affected target resource or application
            applications: App list
            service_graph: Service graph
            blast_report: Blast radius details

        Returns:
            ImpactGraph structure
        """
        nodes: list[ImpactGraphNode] = []
        edges: list[ImpactGraphEdge] = []

        # Add target node
        nodes.append(
            ImpactGraphNode(
                id=target_id,
                name=f"Target: {target_id}",
                type="resource" if target_id.startswith("res-") else "application",
                risk_level="CRITICAL"
            )
        )

        # Add affected applications
        for app_id in blast_report.affected_application_ids:
            app = next((a for a in applications if a.application_id == app_id), None)
            if app:
                nodes.append(
                    ImpactGraphNode(
                        id=app_id,
                        name=app.name,
                        type="application",
                        risk_level=app.criticality.risk_level.value if app.criticality else "HIGH"
                    )
                )
                # Link target to application
                edges.append(
                    ImpactGraphEdge(
                        source=target_id,
                        target=app_id,
                        relationship="degrades_application"
                    )
                )

        # Add affected services
        for svc_id in blast_report.affected_service_ids:
            svc_name = svc_id
            for app in applications:
                for s in app.services:
                    if s.service_id == svc_id:
                        svc_name = s.name
                        break

            nodes.append(
                ImpactGraphNode(
                    id=svc_id,
                    name=svc_name,
                    type="service",
                    risk_level="HIGH"
                )
            )

        # Add service graph links that are in the blast radius
        for source, target in service_graph._graph.edges():
            if source in blast_report.affected_service_ids and target in blast_report.affected_service_ids:
                edges.append(
                    ImpactGraphEdge(
                        source=target,  # since depend-on points target -> source, risk flows source <- target
                        target=source,
                        relationship="cascading_failure"
                    )
                )

        return ImpactGraph(nodes=nodes, edges=edges)
