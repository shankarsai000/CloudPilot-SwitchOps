"""
FastAPI routes for Infrastructure Discovery Agent.

Exposes REST API for:
- Listing all discovered resources
- Filtering by type, provider, region
- Querying resource dependencies
- Discovery statistics and metadata
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ResourceResponse(BaseModel):
    """Resource API response."""

    id: str
    name: str
    type: str
    provider: str
    region: Optional[str] = None
    state: str
    owner: Optional[str] = None
    cost_monthly: Optional[float] = None
    tags: dict = {}
    metadata: dict = {}


class DependencyResponse(BaseModel):
    """Dependency API response."""

    source_id: str
    target_id: str
    relationship_type: str
    metadata: dict = {}


class ResourceGraphResponse(BaseModel):
    """Complete resource graph response."""

    total_resources: int
    resources: list[ResourceResponse]
    dependencies: list[DependencyResponse]
    resources_by_type: dict[str, int]
    resources_by_provider: dict[str, int]
    failures: list[str] = []


class StatisticsResponse(BaseModel):
    """Statistics response."""

    total_resources: int
    by_type: dict[str, int]
    by_provider: dict[str, int]


def create_discovery_router(repository=None, agent=None) -> APIRouter:
    """
    Create FastAPI router for discovery endpoints.

    Args:
        repository: ResourceRepository instance
        agent: DiscoveryAgent instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/discovery", tags=["discovery"])

    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """
        Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "healthy", "service": "discovery-agent"}

    @router.get("/resources", response_model=ResourceGraphResponse)
    async def get_resources(
        provider: Optional[str] = Query(None, description="Filter by cloud provider"),
        resource_type: Optional[str] = Query(None, description="Filter by resource type"),
        region: Optional[str] = Query(None, description="Filter by region"),
        limit: int = Query(100, ge=1, le=10000),
        offset: int = Query(0, ge=0),
    ) -> ResourceGraphResponse:
        """
        List all discovered resources with optional filtering.

        Args:
            provider: Cloud provider filter (aws, azure, gcp, k8s)
            resource_type: Resource type filter
            region: Region filter
            limit: Result limit (max 10000)
            offset: Result offset for pagination

        Returns:
            Paginated list of resources
        """
        if not repository:
            raise HTTPException(status_code=503, detail="Repository not available")

        try:
            all_resources = repository.get_all_resources()

            filtered = [
                r for r in all_resources
                if (not provider or r.provider == provider)
                and (not resource_type or r.type.value == resource_type)
                and (not region or r.region == region)
            ]

            paginated = filtered[offset : offset + limit]

            resources_by_type: dict[str, int] = {}
            resources_by_provider: dict[str, int] = {}

            for r in filtered:
                resources_by_type[r.type.value] = resources_by_type.get(r.type.value, 0) + 1
                resources_by_provider[r.provider] = resources_by_provider.get(r.provider, 0) + 1

            return ResourceGraphResponse(
                total_resources=len(filtered),
                resources=[
                    ResourceResponse(
                        id=r.id,
                        name=r.name,
                        type=r.type.value,
                        provider=r.provider,
                        region=r.region,
                        state=r.state.value,
                        owner=r.owner,
                        cost_monthly=r.cost_monthly,
                        tags=r.tags,
                        metadata=r.metadata,
                    )
                    for r in paginated
                ],
                dependencies=[],
                resources_by_type=resources_by_type,
                resources_by_provider=resources_by_provider,
            )
        except Exception as e:
            logger.error(f"Error fetching resources: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/resources/{resource_id}")
    async def get_resource(resource_id: str) -> ResourceResponse:
        """
        Get single resource by ID.

        Args:
            resource_id: Resource identifier

        Returns:
            Resource details

        Raises:
            HTTPException: If resource not found
        """
        if not repository:
            raise HTTPException(status_code=503, detail="Repository not available")

        try:
            resource = repository.get_resource(resource_id)
            if not resource:
                raise HTTPException(status_code=404, detail="Resource not found")

            return ResourceResponse(
                id=resource.id,
                name=resource.name,
                type=resource.type.value,
                provider=resource.provider,
                region=resource.region,
                state=resource.state.value,
                owner=resource.owner,
                cost_monthly=resource.cost_monthly,
                tags=resource.tags,
                metadata=resource.metadata,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching resource {resource_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/resources/{resource_id}/dependencies")
    async def get_dependencies(
        resource_id: str,
        direction: str = Query("outgoing", pattern="^(outgoing|incoming|both)$"),
    ) -> dict[str, list[DependencyResponse]]:
        """
        Get resource dependencies.

        Args:
            resource_id: Resource identifier
            direction: "outgoing" (what this depends on), "incoming" (what depends on this), "both"

        Returns:
            Dependencies list
        """
        if not repository:
            raise HTTPException(status_code=503, detail="Repository not available")

        try:
            outgoing = []
            incoming = []

            if direction in ["outgoing", "both"]:
                deps = repository.get_resource_dependencies(resource_id)
                outgoing = [
                    DependencyResponse(
                        source_id=d.source_id,
                        target_id=d.target_id,
                        relationship_type=d.relationship_type.value,
                        metadata=d.metadata,
                    )
                    for d in deps
                ]

            if direction in ["incoming", "both"]:
                deps = repository.get_resource_dependents(resource_id)
                incoming = [
                    DependencyResponse(
                        source_id=d.source_id,
                        target_id=d.target_id,
                        relationship_type=d.relationship_type.value,
                        metadata=d.metadata,
                    )
                    for d in deps
                ]

            return {"outgoing": outgoing, "incoming": incoming}
        except Exception as e:
            logger.error(f"Error fetching dependencies for {resource_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/resources/by-type/{resource_type}")
    async def get_resources_by_type(
        resource_type: str,
        limit: int = Query(100, ge=1, le=10000),
    ) -> ResourceGraphResponse:
        """
        Get all resources of a specific type.

        Args:
            resource_type: Resource type identifier
            limit: Result limit

        Returns:
            Resources of specified type
        """
        if not repository:
            raise HTTPException(status_code=503, detail="Repository not available")

        try:
            from models_resource import ResourceType

            try:
                res_type = ResourceType(resource_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid resource type: {resource_type}")

            resources = repository.get_resources_by_type(res_type)
            paginated = resources[:limit]

            return ResourceGraphResponse(
                total_resources=len(resources),
                resources=[
                    ResourceResponse(
                        id=r.id,
                        name=r.name,
                        type=r.type.value,
                        provider=r.provider,
                        region=r.region,
                        state=r.state.value,
                        owner=r.owner,
                        cost_monthly=r.cost_monthly,
                        tags=r.tags,
                        metadata=r.metadata,
                    )
                    for r in paginated
                ],
                dependencies=[],
                resources_by_type={resource_type: len(resources)},
                resources_by_provider={},
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching resources by type {resource_type}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/stats", response_model=StatisticsResponse)
    async def get_statistics() -> StatisticsResponse:
        """
        Get discovery statistics.

        Returns:
            Resource counts by type and provider
        """
        if not repository:
            raise HTTPException(status_code=503, detail="Repository not available")

        try:
            stats = repository.get_statistics()
            return StatisticsResponse(
                total_resources=stats.get("total_resources", 0),
                by_type=stats.get("by_type", {}),
                by_provider=stats.get("by_provider", {}),
            )
        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/discover")
    async def trigger_discovery() -> dict[str, str]:
        """
        Trigger manual discovery run.

        Returns:
            Status message
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Discovery agent not available")

        try:
            logger.info("Manual discovery triggered via API")
            graph = agent.discover()
            
            if repository:
                repository.save_resources(graph.resources, "manual-api")
                repository.save_dependencies(graph.dependencies)

            return {
                "status": "success",
                "resources_discovered": str(graph.total_resources),
                "dependencies": str(len(graph.dependencies)),
            }
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
