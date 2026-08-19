"""
Risk Intelligence API Routes

FastAPI router exposing endpoints for operational risk assessments, policy queries, simulations, and history reports.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models_risk import RiskAssessment, SimulationRequest, SimulationResult, ActionType
from models_impact import BlastRadiusReport
from models_confidence import ConfidenceReport
from risk_intelligence_agent import RiskIntelligenceAgent

logger = logging.getLogger(__name__)


# --- Helper Response Models ---

class RiskSummaryResponse(BaseModel):
    """General summary of risk assessments."""

    total_simulations: int
    critical_risks_count: int
    high_risks_count: int
    compliance_violations_count: int


def create_risk_router(
    agent: Any = None,
    repository: Any = None,
) -> APIRouter:
    """Create FastAPI router for operational risk intelligence agent.

    Args:
        agent: RiskIntelligenceAgent instance
        repository: RiskRepository instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/risk", tags=["risk"])

    # Fallback to direct /risk prefix registrations for route flexibility
    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "healthy", "service": "risk-intelligence-agent"}

    @router.get("", response_model=RiskSummaryResponse)
    async def get_risk_summary() -> RiskSummaryResponse:
        """Get general risk summary.

        Returns:
            General risk metrics
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        history = agent.get_simulation_history()
        critical_count = sum(1 for h in history if h.assessment.risk_score >= 80.0)
        high_count = sum(1 for h in history if 60.0 <= h.assessment.risk_score < 80.0)
        violations = sum(len(h.assessment.policy_violations) for h in history)

        return RiskSummaryResponse(
            total_simulations=len(history),
            critical_risks_count=critical_count,
            high_risks_count=high_count,
            compliance_violations_count=violations
        )

    @router.get("/resources/{id}", response_model=RiskAssessment)
    async def get_resource_risk(
        id: str,
        action: ActionType = Query(ActionType.TERMINATE, description="Infrastructure action simulated"),
    ) -> RiskAssessment:
        """Get predicted risk of action on a resource.

        Args:
            id: Target resource ID
            action: Action simulated

        Returns:
            RiskAssessment report
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        assessment = agent.assess_resource_risk(id, action)
        if not assessment:
            raise HTTPException(status_code=404, detail=f"Resource {id} not found in context")

        if repository:
            try:
                repository.save_assessment(assessment)
            except Exception as e:
                logger.error("Failed to persist assessment: %s", e)

        return assessment

    @router.get("/applications/{id}", response_model=RiskAssessment)
    async def get_application_risk(
        id: str,
        action: ActionType = Query(ActionType.DEPLOY, description="Action simulated"),
    ) -> RiskAssessment:
        """Get predicted risk of action on an application.

        Args:
            id: Target application ID
            action: Action simulated

        Returns:
            RiskAssessment report
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        assessment = agent.assess_application_risk(id, action)
        if not assessment:
            raise HTTPException(status_code=404, detail=f"Application {id} not found in context")

        if repository:
            try:
                repository.save_assessment(assessment)
            except Exception as e:
                logger.error("Failed to persist assessment: %s", e)

        return assessment

    @router.get("/blast-radius/{id}", response_model=BlastRadiusReport)
    async def get_blast_radius(
        id: str,
        action: ActionType = Query(ActionType.TERMINATE, description="Infrastructure action simulated"),
    ) -> BlastRadiusReport:
        """Get blast radius details for resource action.

        Args:
            id: Resource or application ID
            action: Action simulated

        Returns:
            BlastRadiusReport details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        # Run simulation to compute blast radius report
        request = SimulationRequest(target_id=id, action=action)
        result = agent.simulate_action(request)

        return result.blast_radius

    @router.get("/confidence/{id}", response_model=ConfidenceReport)
    async def get_confidence(
        id: str,
        action: ActionType = Query(ActionType.TERMINATE, description="Action simulated"),
    ) -> ConfidenceReport:
        """Get confidence details.

        Args:
            id: Resource or application ID
            action: Action simulated

        Returns:
            ConfidenceReport details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        request = SimulationRequest(target_id=id, action=action)
        result = agent.simulate_action(request)

        # Retrieve confidence details from metadata
        conf_details = result.assessment.metadata.get("confidence_details", {})
        from models_confidence import ConfidenceScore
        score = ConfidenceScore(
            final_score=conf_details.get("final_score", 0.0),
            topology_coverage=conf_details.get("topology_coverage", 0.0),
            historical_incidents=conf_details.get("historical_incidents", 0.0),
            resource_health=conf_details.get("resource_health", 0.0),
            dependency_accuracy=conf_details.get("dependency_accuracy", 0.0),
            business_metadata=conf_details.get("business_metadata", 0.0),
        )

        return ConfidenceReport(
            target_id=id,
            score=score,
            evidence_count=result.assessment.metadata.get("confidence_details", {}).get("evidence_count", 3),
            data_quality_level="MEDIUM",
            notes="Details generated during simulation sequence."
        )

    @router.post("/simulate", response_model=SimulationResult)
    async def simulate_risk(request: SimulationRequest) -> SimulationResult:
        """Simulate change request action.

        Args:
            request: Simulation request parameters

        Returns:
            Full SimulationResult
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            result = agent.simulate_action(request)
            if repository:
                try:
                    repository.save_assessment(result.assessment)
                except Exception as e:
                    logger.error("Failed to persist simulation assessment: %s", e)
            return result
        except Exception as e:
            logger.error("Simulation run failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/policies")
    async def list_policies() -> list[dict[str, Any]]:
        """List configured policy engine rules.

        Returns:
            List of configured rules details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        return agent.get_policies()

    @router.get("/history")
    async def get_history(
        limit: int = Query(50, ge=1, le=1000)
    ) -> list[Any]:
        """Get simulation history records.

        Args:
            limit: Results limit

        Returns:
            List of historical assessment records
        """
        if repository:
            try:
                return repository.get_history(limit)
            except Exception as e:
                logger.error("Database history retrieval failed, falling back to cache: %s", e)

        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        # Fallback to cache log if DB fails/unconfigured
        history = agent.get_simulation_history(limit)
        from models_risk import RiskHistoryRecord
        return [
            RiskHistoryRecord(
                assessment_id=h.assessment.assessment_id,
                target_id=h.request.target_id,
                action=h.request.action.value,
                risk_score=h.assessment.risk_score,
                risk_category=h.assessment.risk_category.value,
                confidence_score=h.assessment.confidence_score,
                policy_violations=h.assessment.policy_violations,
                created_at=h.simulated_at
            )
            for h in history
        ]

    return router
