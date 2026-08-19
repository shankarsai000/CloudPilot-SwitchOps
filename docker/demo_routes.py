"""
FastAPI routes for CloudPilot Demo Environment & Scenario Engine (v2)
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from demo_scenario_engine import ScenarioEngine

logger = logging.getLogger(__name__)

# Single global instance of ScenarioEngine
engine = ScenarioEngine()


class SelectScenarioRequest(BaseModel):
    """Payload to select an enterprise scenario profile."""

    profile: str = "Startup"


class CopilotRequest(BaseModel):
    """Payload for Copilot queries."""

    query: str


def create_demo_router() -> APIRouter:
    """Create FastAPI router for Demo Scenario Engine.

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/demo", tags=["demo"])

    @router.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "demo-scenario-engine"}

    @router.get("/scenarios")
    async def list_scenarios() -> list[dict[str, Any]]:
        """List available enterprise profiles (V2)."""
        return [
            {
                "id": "Startup",
                "name": "Startup Company",
                "description": "20-50 resources, small Kubernetes cluster, monthly cost: $2K-$10K. Simple web deployment.",
            },
            {
                "id": "Healthcare",
                "name": "Healthcare Provider",
                "description": "HIPAA compliance audit logs, highly critical Electronic Health Records database. Spend: $5K-$15K.",
            },
            {
                "id": "Manufacturing",
                "name": "Factory IoT Operations",
                "description": "Continuous sensor data streaming with massive DynamoDB write workload. Spend: $10K-$25K.",
            },
            {
                "id": "Gaming",
                "name": "Multiplayer Game Studio",
                "description": "Matchmaker clustering nodes, Redis lobbying cache, global user traffic. Spend: $15K-$40K.",
            },
            {
                "id": "AI Startup",
                "name": "AI Research Lab",
                "description": "High compute GPU training clusters and model inference APIs. Spend: $250K-$500K.",
            },
            {
                "id": "SaaS",
                "name": "SaaS Platform Company",
                "description": "300-700 resources, multi-service platform, billing replica databases. Spend: $80K-$250K.",
            },
            {
                "id": "Financial Services",
                "name": "Financial Services Group",
                "description": "Strict multi-region transactions compliance records, high availability redundancy. Spend: $2M+.",
            },
            {
                "id": "Government",
                "name": "Civic Portal Administration",
                "description": "Citizen records databases, slow off-peak hours traffic, strict access control rules.",
            },
            {
                "id": "Media",
                "name": "VOD Video Streaming Network",
                "description": "Huge transcoder compute footprint, massive S3 VOD media files storage. Spend: $500K+.",
            },
            {
                "id": "Retail",
                "name": "Global Retail E-commerce",
                "description": "Multi-tier checkout cart services, global CDN load balancers, payment APIs. Spend: $150K+.",
            },
        ]

    @router.post("/select")
    async def select_scenario(request: SelectScenarioRequest) -> dict[str, Any]:
        """Select a scenario and generate its infrastructure data."""
        valid_profiles = {
            "Startup", "Healthcare", "Manufacturing", "Gaming",
            "AI Startup", "AI", "SaaS", "Financial Services",
            "Banking", "Government", "Media", "Retail", "E-commerce"
        }
        if request.profile not in valid_profiles:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid profile '{request.profile}'. Must be one of {valid_profiles}"
            )

        summary = engine.generate_scenario(request.profile)
        # Reset pipeline status
        for key in engine.pipeline_progress:
            engine.pipeline_progress[key] = "PENDING"

        return {
            "status": "success",
            "message": f"Successfully loaded enterprise profile '{request.profile}'",
            "summary": summary,
        }

    @router.get("/telemetry")
    async def get_telemetry(
        target_id: str = Query("ec2-instance-1", description="Resource or App target ID")
    ) -> dict[str, Any]:
        """Fetch live simulated telemetry for a resource."""
        return engine.get_live_telemetry(target_id)

    @router.get("/pipeline-status")
    async def get_pipeline_status() -> dict[str, str]:
        """Get the current progress status of all AI modules (M1-M10)."""
        return engine.pipeline_progress

    @router.post("/pipeline-start")
    async def start_pipeline_run() -> dict[str, str]:
        """Simulate sequential pipeline execution (M1 through M10) for UI animation."""
        logger.info("Starting V2 animated AI pipeline run simulation...")
        import asyncio

        async def run_sim():
            modules = [
                "M1_IDA",
                "M2_CIA",
                "M3_AIA",
                "M4_RIA",
                "M5_SA",
                "M6_DTS",
                "M7_EE",
                "M8_LEA",
                "M9_DE",
                "M10_AEA",
            ]
            for mod in modules:
                engine.pipeline_progress[mod] = "RUNNING"
                await asyncio.sleep(0.4)
                engine.pipeline_progress[mod] = "COMPLETED"

        asyncio.create_task(run_sim())
        return {"status": "started", "message": "Pipeline run simulation started"}

    @router.post("/copilot")
    async def copilot_ask(request: CopilotRequest) -> dict[str, str]:
        """Ask the CloudPilot AI Copilot."""
        response = engine.get_copilot_response(request.query)
        return {"response": response}

    return router
