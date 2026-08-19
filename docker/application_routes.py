"""
Application Intelligence API Routes

FastAPI endpoints for the Application Intelligence Agent.
Exposes REST API for querying applications, topologies,
dependencies, services, ownership, and business criticality.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models_application import (
    Application,
    ApplicationGraph,
    BusinessCriticality,
    OwnershipInfo,
    ServiceNode,
)

logger = logging.getLogger(__name__)


# --- Response Models ---

class ApplicationSummaryResponse(BaseModel):
    """Abbreviated application response for list views."""

    application_id: str
    name: str
    application_type: str
    environment: str
    tier: str
    resource_count: int
    service_count: int
    total_monthly_cost: Optional[float] = None
    discovery_source: str
    criticality_score: Optional[float] = None
    risk_level: Optional[str] = None
    owner: Optional[str] = None
    team: Optional[str] = None


class ApplicationDetailResponse(BaseModel):
    """Full application detail response."""

    application_id: str
    name: str
    description: Optional[str] = None
    application_type: str
    environment: str
    tier: str
    resource_ids: list[str] = []
    service_count: int = 0
    dependency_count: int = 0
    total_monthly_cost: Optional[float] = None
    discovery_source: str = "unknown"
    tags: dict[str, str] = {}
    metadata: dict[str, Any] = {}
    ownership: Optional[dict[str, Any]] = None
    criticality: Optional[dict[str, Any]] = None
    deployment_count: int = 0
    traffic_flow_count: int = 0


class ApplicationListResponse(BaseModel):
    """Paginated application list response."""

    total_applications: int
    applications: list[ApplicationSummaryResponse]
    applications_by_type: dict[str, int] = {}
    applications_by_environment: dict[str, int] = {}
    applications_by_tier: dict[str, int] = {}
    unassigned_resources: int = 0


class TopologyResponse(BaseModel):
    """Application topology response."""

    application_id: str
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    layers: dict[str, list[str]] = {}
    entry_points: list[str] = []
    data_stores: list[str] = []
    depth: int = 0


class DependencyResponse(BaseModel):
    """Application dependency graph response."""

    application_id: Optional[str] = None
    total_nodes: int = 0
    total_edges: int = 0
    has_cycles: bool = False
    max_depth: int = 0
    critical_path: list[str] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []


class ServiceListResponse(BaseModel):
    """Application services response."""

    application_id: str
    total_services: int
    services: list[dict[str, Any]] = []


class OwnershipResponse(BaseModel):
    """Application ownership response."""

    application_id: str
    owner: Optional[str] = None
    team: Optional[str] = None
    team_id: Optional[str] = None
    slack_channel: Optional[str] = None
    email: Optional[str] = None
    repository: Optional[str] = None
    business_unit: Optional[str] = None
    pagerduty_service: Optional[str] = None
    documentation_url: Optional[str] = None
    runbook_url: Optional[str] = None
    confidence: float = 0.0


class CriticalityResponse(BaseModel):
    """Application business criticality response."""

    application_id: str
    revenue_impact: float = 0.0
    compliance_impact: float = 0.0
    availability_target: float = 99.0
    recovery_time_objective_minutes: int = 60
    recovery_point_objective_minutes: int = 15
    risk_level: str = "medium"
    criticality_score: float = 0.0
    compliance_frameworks: list[str] = []
    customer_facing: bool = False
    data_classification: str = "internal"


class StatisticsResponse(BaseModel):
    """Application statistics response."""

    total_applications: int = 0
    total_services: int = 0
    total_dependencies: int = 0
    by_type: dict[str, int] = {}
    by_environment: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    ownership_coverage: float = 0.0
    average_criticality: float = 0.0


# --- Router ---

def create_application_router(
    agent: Any = None,
    repository: Any = None,
) -> APIRouter:
    """Create FastAPI router for application intelligence endpoints.

    Args:
        agent: ApplicationIntelligenceAgent instance
        repository: ApplicationRepository instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/applications", tags=["applications"])

    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "healthy", "service": "application-intelligence-agent"}

    @router.get("", response_model=ApplicationListResponse)
    async def get_applications(
        app_type: Optional[str] = Query(None, description="Filter by application type"),
        environment: Optional[str] = Query(None, description="Filter by environment"),
        tier: Optional[str] = Query(None, description="Filter by service tier"),
        limit: int = Query(100, ge=1, le=10000),
        offset: int = Query(0, ge=0),
    ) -> ApplicationListResponse:
        """List all applications with optional filtering.

        Args:
            app_type: Application type filter
            environment: Environment filter
            tier: Service tier filter
            limit: Result limit
            offset: Pagination offset

        Returns:
            Paginated list of applications
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            graph = agent.get_application_graph()
            if not graph:
                return ApplicationListResponse(total_applications=0, applications=[])

            apps = graph.applications

            # Apply filters
            if app_type:
                apps = [a for a in apps if a.application_type.value == app_type]
            if environment:
                apps = [a for a in apps if a.environment.value == environment]
            if tier:
                apps = [a for a in apps if a.tier.value == tier]

            paginated = apps[offset: offset + limit]

            return ApplicationListResponse(
                total_applications=len(apps),
                applications=[
                    _app_to_summary(a) for a in paginated
                ],
                applications_by_type=graph.applications_by_type,
                applications_by_environment=graph.applications_by_environment,
                applications_by_tier=graph.applications_by_tier,
                unassigned_resources=len(graph.unassigned_resources),
            )
        except Exception as e:
            logger.error("Error fetching applications: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{application_id}", response_model=ApplicationDetailResponse)
    async def get_application(application_id: str) -> ApplicationDetailResponse:
        """Get application details by ID.

        Args:
            application_id: Application identifier

        Returns:
            Full application details

        Raises:
            HTTPException: 404 if not found
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            app = agent.get_application(application_id)
            if not app:
                raise HTTPException(status_code=404, detail="Application not found")

            return _app_to_detail(app)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching application %s: %s", application_id, e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{application_id}/topology", response_model=TopologyResponse)
    async def get_application_topology(
        application_id: str,
    ) -> TopologyResponse:
        """Get application topology.

        Args:
            application_id: Application identifier

        Returns:
            Application topology with nodes, edges, layers
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            topology = agent.get_application_topology(application_id)
            if not topology:
                raise HTTPException(status_code=404, detail="Application not found")

            exporter = agent.get_graph_exporter()
            topo_dict = exporter.topology_to_dict(topology)

            return TopologyResponse(
                application_id=application_id,
                nodes=topo_dict.get("nodes", []),
                edges=topo_dict.get("edges", []),
                layers=topo_dict.get("layers", {}),
                entry_points=topo_dict.get("entry_points", []),
                data_stores=topo_dict.get("data_stores", []),
                depth=topo_dict.get("depth", 0),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching topology for %s: %s", application_id, e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{application_id}/dependencies", response_model=DependencyResponse)
    async def get_application_dependencies(
        application_id: str,
    ) -> DependencyResponse:
        """Get application dependency graph.

        Args:
            application_id: Application identifier

        Returns:
            Dependency graph with nodes, edges, cycles
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            dep_graph = agent.get_application_dependencies(application_id)
            if not dep_graph:
                raise HTTPException(status_code=404, detail="Application not found")

            exporter = agent.get_graph_exporter()
            dep_dict = exporter.dependency_graph_to_dict(dep_graph)

            return DependencyResponse(
                application_id=dep_dict.get("application_id"),
                total_nodes=dep_dict.get("total_nodes", 0),
                total_edges=dep_dict.get("total_edges", 0),
                has_cycles=dep_dict.get("has_cycles", False),
                max_depth=dep_dict.get("max_depth", 0),
                critical_path=dep_dict.get("critical_path", []),
                nodes=dep_dict.get("nodes", []),
                edges=dep_dict.get("edges", []),
                cycles=dep_dict.get("cycles", []),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching dependencies for %s: %s", application_id, e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{application_id}/services", response_model=ServiceListResponse)
    async def get_application_services(
        application_id: str,
    ) -> ServiceListResponse:
        """Get services within an application.

        Args:
            application_id: Application identifier

        Returns:
            List of services
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            app = agent.get_application(application_id)
            if not app:
                raise HTTPException(status_code=404, detail="Application not found")

            services = [
                {
                    "service_id": s.service_id,
                    "name": s.name,
                    "service_type": s.service_type.value if hasattr(s.service_type, "value") else str(s.service_type),
                    "protocol": s.protocol.value if hasattr(s.protocol, "value") else str(s.protocol),
                    "port": s.port,
                    "resource_ids": s.resource_ids,
                    "health_status": s.health_status,
                }
                for s in app.services
            ]

            return ServiceListResponse(
                application_id=application_id,
                total_services=len(services),
                services=services,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching services for %s: %s", application_id, e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{application_id}/owners", response_model=OwnershipResponse)
    async def get_application_owners(
        application_id: str,
    ) -> OwnershipResponse:
        """Get ownership information for an application.

        Args:
            application_id: Application identifier

        Returns:
            Ownership details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            app = agent.get_application(application_id)
            if not app:
                raise HTTPException(status_code=404, detail="Application not found")

            ownership = app.ownership
            if not ownership:
                return OwnershipResponse(application_id=application_id)

            return OwnershipResponse(
                application_id=application_id,
                owner=ownership.owner,
                team=ownership.team,
                team_id=ownership.team_id,
                slack_channel=ownership.slack_channel,
                email=ownership.email,
                repository=ownership.repository,
                business_unit=ownership.business_unit,
                pagerduty_service=ownership.pagerduty_service,
                documentation_url=ownership.documentation_url,
                runbook_url=ownership.runbook_url,
                confidence=ownership.confidence,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching owners for %s: %s", application_id, e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{application_id}/criticality", response_model=CriticalityResponse)
    async def get_application_criticality(
        application_id: str,
    ) -> CriticalityResponse:
        """Get business criticality for an application.

        Args:
            application_id: Application identifier

        Returns:
            Business criticality scores
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            app = agent.get_application(application_id)
            if not app:
                raise HTTPException(status_code=404, detail="Application not found")

            crit = app.criticality
            if not crit:
                return CriticalityResponse(application_id=application_id)

            return CriticalityResponse(
                application_id=application_id,
                revenue_impact=crit.revenue_impact,
                compliance_impact=crit.compliance_impact,
                availability_target=crit.availability_target,
                recovery_time_objective_minutes=crit.recovery_time_objective_minutes,
                recovery_point_objective_minutes=crit.recovery_point_objective_minutes,
                risk_level=crit.risk_level.value,
                criticality_score=crit.criticality_score,
                compliance_frameworks=crit.compliance_frameworks,
                customer_facing=crit.customer_facing,
                data_classification=crit.data_classification,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching criticality for %s: %s", application_id, e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/discover")
    async def trigger_discovery() -> dict[str, str]:
        """Trigger manual application discovery.

        Returns:
            Discovery results summary
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            logger.info("Manual application discovery triggered via API")
            graph = agent.get_application_graph()

            result = {
                "status": "success",
                "applications_discovered": str(graph.total_applications if graph else 0),
                "services": str(graph.total_services if graph else 0),
                "dependencies": str(graph.total_dependencies if graph else 0),
            }

            if repository and graph:
                repository.save_applications(graph.applications)

            return result
        except Exception as e:
            logger.error("Discovery failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/stats", response_model=StatisticsResponse)
    async def get_statistics() -> StatisticsResponse:
        """Get application intelligence statistics.

        Returns:
            Statistics summary
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            graph = agent.get_application_graph()
            if not graph:
                return StatisticsResponse()

            # Calculate ownership coverage
            owned = sum(
                1 for a in graph.applications if a.ownership and a.ownership.owner
            )
            coverage = (owned / len(graph.applications) * 100) if graph.applications else 0.0

            # Calculate average criticality
            scores = [
                a.criticality.criticality_score
                for a in graph.applications
                if a.criticality
            ]
            avg_crit = sum(scores) / len(scores) if scores else 0.0

            return StatisticsResponse(
                total_applications=graph.total_applications,
                total_services=graph.total_services,
                total_dependencies=graph.total_dependencies,
                by_type=graph.applications_by_type,
                by_environment=graph.applications_by_environment,
                by_tier=graph.applications_by_tier,
                ownership_coverage=round(coverage, 1),
                average_criticality=round(avg_crit, 1),
            )
        except Exception as e:
            logger.error("Error fetching statistics: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    return router


# --- Helper Functions ---

def _app_to_summary(app: Application) -> ApplicationSummaryResponse:
    """Convert Application to summary response.

    Args:
        app: Application model

    Returns:
        ApplicationSummaryResponse
    """
    return ApplicationSummaryResponse(
        application_id=app.application_id,
        name=app.name,
        application_type=app.application_type.value,
        environment=app.environment.value,
        tier=app.tier.value,
        resource_count=len(app.resource_ids),
        service_count=len(app.services),
        total_monthly_cost=app.total_monthly_cost,
        discovery_source=app.discovery_source,
        criticality_score=(
            app.criticality.criticality_score if app.criticality else None
        ),
        risk_level=(
            app.criticality.risk_level.value if app.criticality else None
        ),
        owner=app.ownership.owner if app.ownership else None,
        team=app.ownership.team if app.ownership else None,
    )


def _app_to_detail(app: Application) -> ApplicationDetailResponse:
    """Convert Application to detail response.

    Args:
        app: Application model

    Returns:
        ApplicationDetailResponse
    """
    ownership_dict = None
    if app.ownership:
        ownership_dict = {
            "owner": app.ownership.owner,
            "team": app.ownership.team,
            "team_id": app.ownership.team_id,
            "slack_channel": app.ownership.slack_channel,
            "email": app.ownership.email,
            "repository": app.ownership.repository,
            "business_unit": app.ownership.business_unit,
            "pagerduty_service": app.ownership.pagerduty_service,
            "confidence": app.ownership.confidence,
        }

    criticality_dict = None
    if app.criticality:
        criticality_dict = {
            "criticality_score": app.criticality.criticality_score,
            "risk_level": app.criticality.risk_level.value,
            "revenue_impact": app.criticality.revenue_impact,
            "compliance_impact": app.criticality.compliance_impact,
            "availability_target": app.criticality.availability_target,
            "customer_facing": app.criticality.customer_facing,
        }

    return ApplicationDetailResponse(
        application_id=app.application_id,
        name=app.name,
        description=app.description,
        application_type=app.application_type.value,
        environment=app.environment.value,
        tier=app.tier.value,
        resource_ids=app.resource_ids,
        service_count=len(app.services),
        dependency_count=len(app.dependencies),
        total_monthly_cost=app.total_monthly_cost,
        discovery_source=app.discovery_source,
        tags=app.tags,
        metadata=app.metadata,
        ownership=ownership_dict,
        criticality=criticality_dict,
        deployment_count=len(app.deployments),
        traffic_flow_count=len(app.traffic_flows),
    )
