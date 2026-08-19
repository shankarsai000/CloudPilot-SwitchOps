"""
Explainability API Routes

FastAPI router exposing endpoints for decision explanations, executive summaries, technical markdown, compliance reports, and visual graphs.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models_explanation import ExplanationReport, ConfidenceBreakdown, EvidenceGraph, AuditTrail
from explainability_agent import ExplainabilityAgent

logger = logging.getLogger(__name__)


def create_explanation_router(
    agent: Any = None,
    repository: Any = None,
) -> APIRouter:
    """Create FastAPI router for Explainability Engine Agent.

    Args:
        agent: ExplainabilityAgent instance
        repository: ExplanationRepository instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api", tags=["explainability"])

    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "healthy", "service": "explainability-engine"}

    @router.get("/explanations/{decision}", response_model=ExplanationReport)
    async def get_explanation(
        decision: str,
        target_id: str = Query(..., description="Target Resource/Application ID to explain")
    ) -> ExplanationReport:
        """Retrieve natural language explanation report for a specific decision.

        Returns:
            ExplanationReport details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            report = agent.explain_decision(decision, target_id)
            if repository:
                try:
                    repository.save_explanation(report)
                except Exception as e:
                    logger.error("Failed to persist explanation: %s", e)
            return report
        except Exception as e:
            logger.error("Failed to generate explanation: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/reports/executive")
    async def get_executive_report(
        decision_id: str = Query(..., description="Decision ID"),
        target_id: str = Query(..., description="Target Resource ID")
    ) -> dict[str, str]:
        """Retrieve executive report.

        Returns:
            Executive summary text
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        reports = agent.generate_natural_reports(decision_id, target_id)
        return {"report": reports.get("executive", "")}

    @router.get("/reports/technical")
    async def get_technical_report(
        decision_id: str = Query(..., description="Decision ID"),
        target_id: str = Query(..., description="Target Resource ID")
    ) -> dict[str, str]:
        """Retrieve technical engineering markdown report.

        Returns:
            Technical markdown text
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        reports = agent.generate_natural_reports(decision_id, target_id)
        return {"report": reports.get("technical", "")}

    @router.get("/reports/compliance")
    async def get_compliance_report(
        decision_id: str = Query(..., description="Decision ID"),
        target_id: str = Query(..., description="Target Resource ID")
    ) -> dict[str, str]:
        """Retrieve compliance audit report.

        Returns:
            Compliance audit text
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        reports = agent.generate_natural_reports(decision_id, target_id)
        return {"report": reports.get("compliance", "")}

    @router.get("/confidence/{decision}", response_model=ConfidenceBreakdown)
    async def get_confidence_breakdown(
        decision: str,
        target_id: str = Query(..., description="Target ID")
    ) -> ConfidenceBreakdown:
        """Retrieve confidence breakdown parameters.

        Returns:
            ConfidenceBreakdown details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        return agent.get_confidence_breakdown(decision, target_id)

    @router.get("/evidence/{decision}", response_model=EvidenceGraph)
    async def get_evidence_graph(
        decision: str,
        target_id: str = Query(..., description="Target ID")
    ) -> EvidenceGraph:
        """Retrieve visual evidence graph relations.

        Returns:
            EvidenceGraph structure
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        return agent.get_evidence_graph(decision, target_id)

    @router.get("/audit", response_model=list[AuditTrail])
    async def list_audit_trail(
        limit: int = Query(50, ge=1, le=1000)
    ) -> list[AuditTrail]:
        """Retrieve immutable audit logs.

        Returns:
            List of AuditTrail logs
        """
        if repository:
            try:
                return repository.get_audit_trail(limit)
            except Exception as e:
                logger.error("DB audit logs fetch failed: %s", e)

        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        return agent.get_audit_trail(limit)

    return router
