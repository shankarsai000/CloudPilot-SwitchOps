"""
Learning API Routes

FastAPI router exposing endpoints for Cloud DNA profiles, patterns,
organizational history, experience replay, feedback, and retraining.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models_learning import (
    CloudDNAProfile,
    FeedbackVerdict,
    LearningMetrics,
    PatternRecord,
)
from learning_agent import LearningAgent

logger = logging.getLogger(__name__)


# --- Request Models ---


class FeedbackRequest(BaseModel):
    """Payload to submit human feedback."""

    decision_id: str
    source: str
    verdict: FeedbackVerdict
    reason: str = ""
    tags: list[str] = Field(default_factory=list)


class ExperienceQueryRequest(BaseModel):
    """Payload to query experience replay."""

    context: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=50)


def create_learning_router(
    agent: Any = None,
    repository: Any = None,
) -> APIRouter:
    """Create FastAPI router for Learning Agent.

    Args:
        agent: LearningAgent instance
        repository: LearningRepository instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/learning", tags=["learning"])

    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "healthy", "service": "learning-agent"}

    @router.get("/profile")
    async def get_profile() -> dict[str, Any]:
        """Retrieve learning agent profile summary.

        Returns:
            Profile summary dict
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.get_profile_summary()

    @router.get("/cloud-dna", response_model=CloudDNAProfile)
    async def get_cloud_dna() -> CloudDNAProfile:
        """Retrieve current Cloud DNA profile.

        Returns:
            CloudDNAProfile
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.get_cloud_dna()

    @router.get("/patterns", response_model=list[PatternRecord])
    async def get_patterns() -> list[PatternRecord]:
        """Retrieve detected recurring patterns.

        Returns:
            List of PatternRecord instances
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.get_patterns()

    @router.get("/history")
    async def get_history(
        limit: int = Query(50, ge=1, le=1000)
    ) -> list[dict[str, Any]]:
        """Retrieve organizational memory event history.

        Returns:
            List of event dicts
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        events = agent.get_history(limit)
        return [e.dict() for e in events]

    @router.get("/experience")
    async def get_experience(
        target_id: str = Query("", description="Target ID to search for"),
        event_type: str = Query("", description="Event type to search for"),
        top_k: int = Query(5, ge=1, le=50),
    ) -> list[dict[str, Any]]:
        """Query experience replay for similar historical outcomes.

        Returns:
            List of experience record dicts
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        context: dict[str, Any] = {}
        if target_id:
            context["target_id"] = target_id
        if event_type:
            context["event_type"] = event_type
        experiences = agent.find_similar_experiences(context, top_k)
        return [e.dict() for e in experiences]

    @router.get("/recommendations")
    async def get_recommendations() -> list[dict[str, Any]]:
        """Retrieve optimized recommendation scores.

        Returns:
            List of per-action stats
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.get_recommendation_stats()

    @router.post("/feedback")
    async def submit_feedback(request: FeedbackRequest) -> dict[str, str]:
        """Submit human feedback on a recommendation.

        Returns:
            Feedback confirmation
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.submit_feedback(
            request.decision_id,
            request.source,
            request.verdict,
            request.reason,
            request.tags,
        )

    @router.post("/retrain")
    async def retrain() -> dict[str, Any]:
        """Trigger learning pipeline re-evaluation.

        Returns:
            Retrain results summary
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.retrain()

    return router
