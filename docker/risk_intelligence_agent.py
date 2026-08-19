"""
Risk Intelligence Agent — Main Orchestrator

Consumes M1 (discovery), M2 (costs), and M3 (applications) data representations.
Performs simulation requests and assesses operational risks.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from models_resource import ResourceGraph
from models_application import ApplicationGraph
from models_risk import RiskAssessment, SimulationRequest, SimulationResult, ActionType, RiskCategory
from models_impact import BlastRadiusReport, ImpactGraph
from risk_engine import RiskEngine

logger = logging.getLogger(__name__)


class RiskIntelligenceAgent:
    """Orchestrates Risk Intelligence runs, simulates operations, and keeps logs of predictions."""

    def __init__(
        self,
        risk_engine: Optional[RiskEngine] = None,
        m1_repo: Optional[Any] = None,
        m2_repo: Optional[Any] = None,
        m3_repo: Optional[Any] = None,
    ) -> None:
        """Initialize the Risk Intelligence Agent.

        Args:
            risk_engine: Risk Engine instance
            m1_repo: M1 resource repository reference
            m2_repo: M2 cost repository reference
            m3_repo: M3 application repository reference
        """
        self.risk_engine = risk_engine or RiskEngine()
        self.m1_repo = m1_repo
        self.m2_repo = m2_repo
        self.m3_repo = m3_repo

        # Staged/discovered runtime graphs (if repos are not running/configured)
        self._resources_cache: list[Any] = []
        self._applications_cache: list[Any] = []
        self._service_graph_cache: Optional[Any] = None
        self._history_log: list[SimulationResult] = []

        logger.info("RiskIntelligenceAgent initialized successfully")

    def load_context_data(
        self,
        resource_graph: ResourceGraph,
        app_graph: ApplicationGraph,
        service_graph: Any
    ) -> None:
        """Load operational environment context cache.

        Args:
            resource_graph: Discovered M1 resources
            app_graph: Discovered M3 applications
            service_graph: M3 service dependency graph
        """
        self._resources_cache = resource_graph.resources
        self._applications_cache = app_graph.applications
        self._service_graph_cache = service_graph
        logger.info(
            "Loaded context: %d resources, %d applications",
            len(self._resources_cache),
            len(self._applications_cache)
        )

    def assess_resource_risk(
        self,
        resource_id: str,
        action: ActionType = ActionType.TERMINATE,
        parameters: Optional[dict[str, Any]] = None
    ) -> Optional[RiskAssessment]:
        """Assess the predicted risk of performing an action on a specific resource.

        Args:
            resource_id: Resource identifier
            action: Action simulated
            parameters: Action parameters

        Returns:
            RiskAssessment report or None if resource not found
        """
        resources = self._get_resources()
        target_res = next((r for r in resources if r.id == resource_id), None)
        if not target_res:
            logger.warning("Resource %s not found in discovery cache", resource_id)
            return None

        apps = self._get_applications()
        # Find if resource belongs to an application context
        target_app = None
        for app in apps:
            if resource_id in app.resource_ids:
                target_app = app
                break

        service_graph = self._get_service_graph()
        params = parameters or {}

        # Query historical incident count from cache/logs (stubeed to 1 for payments, 0 otherwise)
        historical_incidents = 2 if target_app and "payment" in target_app.name.lower() else 0

        assessment, blast, graph, timeline = self.risk_engine.assess_risk(
            resource_id,
            target_res,
            target_app,
            resources,
            apps,
            service_graph,
            action,
            params,
            historical_incidents
        )

        # Log to simulation history
        sim_result = SimulationResult(
            simulation_id=f"sim-{uuid.uuid4().hex[:12]}",
            request=SimulationRequest(target_id=resource_id, action=action, parameters=params),
            assessment=assessment,
            blast_radius=blast,
            impact_graph=graph,
            timeline=timeline,
            simulated_at=datetime.utcnow()
        )
        self._history_log.append(sim_result)

        return assessment

    def assess_application_risk(
        self,
        application_id: str,
        action: ActionType = ActionType.DEPLOY,
        parameters: Optional[dict[str, Any]] = None
    ) -> Optional[RiskAssessment]:
        """Assess the predicted risk of performing an action on a specific application.

        Args:
            application_id: Application identifier
            action: Action simulated
            parameters: Action parameters

        Returns:
            RiskAssessment report or None if application not found
        """
        apps = self._get_applications()
        target_app = next((a for a in apps if a.application_id == application_id), None)
        if not target_app:
            logger.warning("Application %s not found in cache", application_id)
            return None

        resources = self._get_resources()
        service_graph = self._get_service_graph()
        params = parameters or {}

        # Heuristic: analyze risk on application level (typically deploys or restarts)
        historical_incidents = 3 if "payment" in target_app.name.lower() else 1

        assessment, blast, graph, timeline = self.risk_engine.assess_risk(
            application_id,
            None,
            target_app,
            resources,
            apps,
            service_graph,
            action,
            params,
            historical_incidents
        )

        # Log to simulation history
        sim_result = SimulationResult(
            simulation_id=f"sim-{uuid.uuid4().hex[:12]}",
            request=SimulationRequest(target_id=application_id, action=action, parameters=params),
            assessment=assessment,
            blast_radius=blast,
            impact_graph=graph,
            timeline=timeline,
            simulated_at=datetime.utcnow()
        )
        self._history_log.append(sim_result)

        return assessment

    def simulate_action(self, request: SimulationRequest) -> SimulationResult:
        """Simulate a change request and return the complete SimulationResult report.

        Args:
            request: SimulationRequest details

        Returns:
            SimulationResult containing assessment, blast radius, timeline, and mitigation details
        """
        resources = self._get_resources()
        apps = self._get_applications()
        service_graph = self._get_service_graph()

        target_res = next((r for r in resources if r.id == request.target_id), None)
        target_app = next((a for a in apps if a.application_id == request.target_id), None)

        if not target_res and not target_app:
            # Create a mock resource if target is not matched (enables API robustness)
            from models_resource import ResourceType, ResourceState
            target_res = CloudResource(
                id=request.target_id,
                name=f"Mock-{request.target_id}",
                type=ResourceType.EC2_INSTANCE,
                provider="aws",
                state=ResourceState.RUNNING,
                tags={"env": "production"}
            )
            resources.append(target_res)

        if target_res and not target_app:
            for app in apps:
                if request.target_id in app.resource_ids:
                    target_app = app
                    break

        historical_incidents = 2 if target_app and "payment" in target_app.name.lower() else 0

        assessment, blast, graph, timeline = self.risk_engine.assess_risk(
            request.target_id,
            target_res,
            target_app,
            resources,
            apps,
            service_graph,
            request.action,
            request.parameters,
            historical_incidents
        )

        sim_result = SimulationResult(
            simulation_id=f"sim-{uuid.uuid4().hex[:12]}",
            request=request,
            assessment=assessment,
            blast_radius=blast,
            impact_graph=graph,
            timeline=timeline,
            simulated_at=datetime.utcnow()
        )
        self._history_log.append(sim_result)

        return sim_result

    def get_simulation_history(self, limit: int = 50) -> list[SimulationResult]:
        """Retrieve recent simulation runs.

        Args:
            limit: History retrieval limit

        Returns:
            List of SimulationResult objects sorted newest first
        """
        return sorted(self._history_log, key=lambda r: r.simulated_at, reverse=True)[:limit]

    def get_policies(self) -> list[dict[str, Any]]:
        """List configured policy engine rules.

        Returns:
            List of configured policy detail dicts
        """
        return self.risk_engine.policy_engine.get_configured_policies()

    def _get_resources(self) -> list[Any]:
        """Fetch resources from repository or cache fallback."""
        if self.m1_repo:
            try:
                return self.m1_repo.get_all_resources()
            except Exception:
                pass
        return self._resources_cache

    def _get_applications(self) -> list[Application]:
        """Fetch applications from repository or cache fallback."""
        if self.m3_repo:
            try:
                return self.m3_repo.get_all_applications()
            except Exception:
                pass
        return self._applications_cache

    def _get_service_graph(self) -> Any:
        """Fetch service dependency graph from cache or mock default."""
        if self._service_graph_cache:
            return self._service_graph_cache
        
        # Build empty ServiceGraph context for safety
        from service_graph import ServiceGraph
        return ServiceGraph()
