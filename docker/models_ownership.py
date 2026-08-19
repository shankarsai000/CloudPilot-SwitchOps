"""
Application Intelligence Agent - Ownership Models

Defines models for team ownership, contact information,
and organizational mapping of applications.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class EscalationContact(BaseModel):
    """Single contact in an escalation chain."""

    level: int = Field(..., ge=1, le=5, description="Escalation level (1=primary)")
    name: str = Field(..., description="Contact name")
    role: str = Field(default="engineer", description="Contact role")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    slack_handle: Optional[str] = Field(None, description="Slack handle")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "level": 1,
                "name": "Jane Doe",
                "role": "SRE",
                "email": "jane.doe@company.com",
                "slack_handle": "@jane.doe",
            }
        }


class TeamInfo(BaseModel):
    """Detailed team information with contact details and escalation chain."""

    team_id: str = Field(..., description="Unique team identifier")
    team_name: str = Field(..., description="Human-readable team name")
    business_unit: Optional[str] = Field(None, description="Business unit")
    cost_center: Optional[str] = Field(None, description="Cost center code")
    manager: Optional[str] = Field(None, description="Team manager name")
    email: Optional[str] = Field(None, description="Team email")
    slack_channel: Optional[str] = Field(None, description="Primary Slack channel")
    pagerduty_service_id: Optional[str] = Field(None, description="PagerDuty service ID")
    escalation_contacts: list[EscalationContact] = Field(
        default_factory=list, description="Escalation chain"
    )
    member_count: int = Field(default=0, ge=0, description="Number of team members")
    repositories: list[str] = Field(
        default_factory=list, description="Team-owned repositories"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "team_id": "team-payments",
                "team_name": "Payments Engineering",
                "business_unit": "Commerce",
                "cost_center": "CC-4200",
                "manager": "John Smith",
                "email": "payments-eng@company.com",
                "slack_channel": "#payments-eng",
                "pagerduty_service_id": "PD-PAY-001",
                "member_count": 8,
                "repositories": [
                    "https://github.com/org/payment-service",
                    "https://github.com/org/billing-service",
                ],
            }
        }


class OwnershipMapping(BaseModel):
    """Mapping between an application and its owning team."""

    application_id: str = Field(..., description="Application identifier")
    application_name: str = Field(..., description="Application name")
    team: Optional[TeamInfo] = Field(None, description="Owning team details")
    primary_owner: Optional[str] = Field(None, description="Primary owner individual")
    secondary_owner: Optional[str] = Field(None, description="Secondary owner individual")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Confidence score of ownership resolution"
    )
    resolution_source: str = Field(
        default="unknown",
        description="How ownership was resolved (tag, annotation, codeowners, manual)"
    )
    verified: bool = Field(
        default=False, description="Whether ownership has been manually verified"
    )
    last_verified_at: Optional[datetime] = Field(
        None, description="Last manual verification timestamp"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "application_id": "app-payment-service",
                "application_name": "Payment Service",
                "primary_owner": "jane.doe",
                "confidence": 0.95,
                "resolution_source": "tag",
                "verified": True,
            }
        }


class OwnershipReport(BaseModel):
    """Aggregate ownership coverage report across all applications."""

    total_applications: int = Field(
        default=0, ge=0, description="Total applications assessed"
    )
    owned_applications: int = Field(
        default=0, ge=0, description="Applications with assigned ownership"
    )
    unowned_applications: int = Field(
        default=0, ge=0, description="Applications without ownership"
    )
    coverage_percentage: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Ownership coverage %"
    )
    average_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Average confidence score"
    )
    by_team: dict[str, int] = Field(
        default_factory=dict,
        description="Application count by team"
    )
    by_resolution_source: dict[str, int] = Field(
        default_factory=dict,
        description="Application count by resolution source"
    )
    unverified_count: int = Field(
        default=0, ge=0, description="Number of unverified mappings"
    )
    mappings: list[OwnershipMapping] = Field(
        default_factory=list, description="All ownership mappings"
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Report generation timestamp"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "total_applications": 12,
                "owned_applications": 10,
                "unowned_applications": 2,
                "coverage_percentage": 83.3,
                "average_confidence": 0.85,
                "by_team": {"Payments": 3, "Platform": 4, "Frontend": 3},
                "by_resolution_source": {"tag": 6, "annotation": 3, "manual": 1},
                "unverified_count": 4,
            }
        }
