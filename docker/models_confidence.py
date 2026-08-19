"""
Risk Intelligence Agent - Pydantic Models for Confidence Scoring

Defines confidence metrics and calculation breakdowns.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ConfidenceScore(BaseModel):
    """Detailed components and calculation of the final confidence percentage."""

    final_score: float = Field(..., ge=0.0, le=100.0, description="Weighted final confidence score (0-100%)")
    topology_coverage: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from topological mapping completeness (weight: 30%)")
    historical_incidents: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from historical incident logs availability (weight: 20%)")
    resource_health: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from current resource health signals (weight: 20%)")
    dependency_accuracy: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from verified dependency accuracy (weight: 20%)")
    business_metadata: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from completeness of business/owner tags (weight: 10%)")


class ConfidenceReport(BaseModel):
    """A complete report for a confidence calculation event."""

    target_id: str = Field(..., description="The resource or application ID being evaluated")
    score: ConfidenceScore = Field(..., description="Calculation score details")
    evidence_count: int = Field(default=0, ge=0, description="Number of concrete evidence factors used in the calculations")
    data_quality_level: str = Field(default="MEDIUM", description="Inferred quality of raw metadata (HIGH, MEDIUM, LOW)")
    notes: Optional[str] = Field(None, description="Explanatory notes regarding the confidence calculations")
