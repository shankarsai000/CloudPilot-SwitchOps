"""
Digital Twin Builder Component

Builder Pattern to construct the virtual representative model (DigitalTwin)
from discover, cost, and application context parameters.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from models_resource import CloudResource
from models_application import Application
from models_simulation import DigitalTwin

logger = logging.getLogger(__name__)


class TwinBuilder:
    """Assembles the DigitalTwin virtual state model."""

    def __init__(self) -> None:
        """Initialize Twin Builder."""
        self._resources: list[dict[str, Any]] = []
        self._applications: list[dict[str, Any]] = []
        self._cost_model: dict[str, Any] = {}
        self._dependency_graph: dict[str, Any] = {}
        self._policies: list[dict[str, Any]] = []

    def with_resources(self, resources: list[CloudResource]) -> TwinBuilder:
        """Add resource states.

        Args:
            resources: Cloud resources

        Returns:
            Builder instance
        """
        self._resources = [
            {
                "id": r.id,
                "name": r.name,
                "type": r.type.value,
                "state": r.state.value,
                "tags": r.tags,
                "metadata": r.metadata,
                "cost_monthly": r.cost_monthly or 0.0
            }
            for r in resources
        ]
        return self

    def with_applications(self, applications: list[Application]) -> TwinBuilder:
        """Add application states.

        Args:
            applications: Applications

        Returns:
            Builder instance
        """
        self._applications = [
            {
                "application_id": app.application_id,
                "name": app.name,
                "tier": app.tier.value if hasattr(app.tier, "value") else str(app.tier),
                "environment": app.environment.value if hasattr(app.environment, "value") else str(app.environment),
                "resource_ids": app.resource_ids,
                "total_monthly_cost": app.total_monthly_cost or 0.0,
                "services": [
                    {
                        "service_id": s.service_id,
                        "name": s.name,
                        "service_type": s.service_type.value if hasattr(s.service_type, "value") else str(s.service_type),
                        "resource_ids": s.resource_ids
                    }
                    for s in app.services
                ]
            }
            for app in applications
        ]
        return self

    def with_cost_model(self, cost_events: list[Any]) -> TwinBuilder:
        """Calculate and attach financial correlations.

        Args:
            cost_events: Cost metrics

        Returns:
            Builder instance
        """
        total_bill = sum(getattr(e, "daily_cost", 0.0) * 30 for e in cost_events) if cost_events else 0.0
        self._cost_model = {
            "total_monthly_bill_estimate": total_bill,
            "billing_events_count": len(cost_events) if cost_events else 0
        }
        return self

    def with_dependencies(self, service_graph: Any) -> TwinBuilder:
        """Attach dependency structures.

        Args:
            service_graph: ServiceGraph instance

        Returns:
            Builder instance
        """
        if service_graph and hasattr(service_graph, "export_to_dict"):
            self._dependency_graph = service_graph.export_to_dict()
        else:
            self._dependency_graph = {"nodes": [], "edges": []}
        return self

    def with_policies(self, policies: list[dict[str, Any]]) -> TwinBuilder:
        """Attach policy rules.

        Args:
            policies: Configured policies

        Returns:
            Builder instance
        """
        self._policies = policies
        return self

    def build(self) -> DigitalTwin:
        """Generate the completed DigitalTwin model.

        Returns:
            DigitalTwin object
        """
        twin = DigitalTwin(
            twin_id=f"twin-{uuid.uuid4().hex[:12]}",
            resources=self._resources,
            applications=self._applications,
            cost_model=self._cost_model,
            dependency_graph=self._dependency_graph,
            policies=self._policies,
            snapshot_time=datetime.utcnow()
        )
        logger.info("Built DigitalTwin state representation: %s", twin.twin_id)
        return twin
