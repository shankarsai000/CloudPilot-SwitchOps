"""
CloudPilot SwitchOps — Constraint Validation Contracts

Defines the structure for hard operational boundaries, mandatory security bars,
reliability thresholds, and budget constraints.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConstraintType(str, Enum):
    """Categorization of hard constraints."""
    SECURITY = "SECURITY"
    RELIABILITY = "RELIABILITY"
    FINANCIAL = "FINANCIAL"
    OPERATIONAL = "OPERATIONAL"


class ConstraintStatus(str, Enum):
    """Evaluation status of a constraint rule."""
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ConstraintSeverity(str, Enum):
    """Enforcement severity."""
    MANDATORY = "MANDATORY"  # Hard constraint: violation strictly excludes candidate
    ADVISORY = "ADVISORY"    # Soft guideline: generates warnings, affects simplicity score


class ConstraintResult(BaseModel):
    """
    Result of evaluating an individual constraint against a candidate change.
    """
    constraint_id: str = Field(..., description="Stable rule identifier e.g. CONST-SEC-01")
    constraint_type: ConstraintType
    severity: ConstraintSeverity = Field(default=ConstraintSeverity.MANDATORY)
    status: ConstraintStatus
    reason: str = Field(..., description="Clear explanation of the evaluation outcome")
    affected_candidate_ids: List[str] = Field(default_factory=list)
    evidence_refs: Dict[str, Any] = Field(default_factory=dict)
    policy_version: str = Field(default="1.0")

    @property
    def passed(self) -> bool:
        """Returns True if the constraint passed."""
        return self.status == ConstraintStatus.PASS

    @property
    def is_blocking(self) -> bool:
        """Returns True if this constraint result prevents candidate feasibility."""
        return self.severity == ConstraintSeverity.MANDATORY and self.status in (
            ConstraintStatus.FAIL,
            ConstraintStatus.UNKNOWN,
        )
