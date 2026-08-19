"""
Simulation API Routes

FastAPI router exposing endpoints for M6 Digital Twin simulations, scenarios, and safety reports.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models_simulation import SimulationReport, RollbackReport, ScenarioComparison
from digital_twin_agent import DigitalTwinAgent

logger = logging.getLogger(__name__)


# --- Helper Request Models ---

class SimulationRunRequest(BaseModel):
    """Payload to trigger new simulation run."""

    target_id: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    policy_violations: list[str] = Field(default_factory=list)


def create_simulation_router(
    agent: Any = None,
    repository: Any = None,
) -> APIRouter:
    """Create FastAPI router for Digital Twin Simulation Agent.

    Args:
        agent: DigitalTwinAgent instance
        repository: SimulationRepository instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/simulation", tags=["simulation"])

    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "healthy", "service": "digital-twin-simulation-agent"}

    @router.post("/run", response_model=SimulationReport)
    async def run_simulation(request: SimulationRunRequest) -> SimulationReport:
        """Run simulated operational changes against the active virtual twin.

        Returns:
            SimulationReport details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        report = agent.run_simulation(
            request.target_id,
            request.action,
            request.parameters,
            request.policy_violations
        )
        if not report:
            raise HTTPException(status_code=400, detail="Twin state model has not been initialized.")

        if repository:
            try:
                repository.save_simulation(report)
            except Exception as e:
                logger.error("Failed to persist simulation report %s: %s", report.simulation_id, e)

        return report

    @router.get("/scenarios")
    async def get_scenarios(
        target_id: str = Query(..., description="Target ID to simulate scenarios over"),
        scenario_type: str = Query("DISASTER_RECOVERY", description="DR or migration scenario type")
    ) -> dict[str, Any]:
        """List active simulation scenario outcomes.

        Returns:
            Simulated scenario details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        return agent.simulate_scenario(scenario_type, target_id)

    @router.get("/safety")
    async def get_safety_summary(
        target_id: str = Query(..., description="Resource or Application ID"),
        action: str = Query("TERMINATE", description="Action to simulate")
    ) -> dict[str, Any]:
        """Retrieve safety score reports.

        Returns:
            Safety metrics summary
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        report = agent.run_simulation(target_id, action)
        if not report:
            raise HTTPException(status_code=400, detail="Twin state model has not been initialized.")

        return {
            "target_id": target_id,
            "action": action,
            "safety_score": report.safety_score,
            "safety_status": report.safety_status
        }

    @router.get("/rollback", response_model=RollbackReport)
    async def get_rollback_report(
        target_id: str = Query(..., description="Resource or Application ID"),
        action: str = Query("TERMINATE", description="Action to simulate")
    ) -> RollbackReport:
        """Fetch rollback predictions.

        Returns:
            RollbackReport details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        report = agent.run_simulation(target_id, action)
        if not report:
            raise HTTPException(status_code=400, detail="Twin state model has not been initialized.")

        return report.rollback

    @router.get("/report", response_model=list[SimulationReport])
    async def list_simulation_reports(
        limit: int = Query(50, ge=1, le=1000)
    ) -> list[SimulationReport]:
        """Retrieve simulation reports.

        Returns:
            List of SimulationReport objects
        """
        if repository:
            try:
                return repository.get_history(limit)
            except Exception as e:
                logger.error("DB history fetch failed, falling back to agent log: %s", e)

        # Mock list
        return []

    @router.get("/{id}", response_model=SimulationReport)
    async def get_simulation(id: str) -> SimulationReport:
        """Get simulation details by ID.

        Args:
            id: Simulation ID

        Returns:
            SimulationReport details
        """
        if repository:
            try:
                report = repository.get_simulation(id)
                if report:
                    return report
            except Exception:
                pass

        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        report = agent.get_simulation_report(id)
        if not report:
            raise HTTPException(status_code=404, detail=f"Simulation {id} not found")

        return report

    return router
