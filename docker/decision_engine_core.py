"""
Decision Engine Core Component

Orchestrates the Decision Council pipeline: gathers votes, runs consensus manager,
scores proposals, resolves conflicts, validates policies, calculates aggregate confidence,
logs audits, and builds execution packages.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from models_decision import (
    AgentVote,
    ApprovalLevel,
    DecisionRecord,
    DecisionState,
    VoteVerdict,
)
from consensus_manager import ConsensusManager
from scoring_engine_decision import ScoringEngineDecision
from conflict_resolver import ConflictResolver
from approval_router import ApprovalRouter
from policy_validator import PolicyValidator
from confidence_calculator_decision import ConfidenceCalculatorDecision
from execution_package_builder import ExecutionPackageBuilder
from audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class DecisionEngineCore:
    """Core reasoning engine representing the Decision Council Orchestrator."""

    def __init__(
        self,
        consensus_manager: Optional[ConsensusManager] = None,
        scoring_engine: Optional[ScoringEngineDecision] = None,
        conflict_resolver: Optional[ConflictResolver] = None,
        approval_router: Optional[ApprovalRouter] = None,
        policy_validator: Optional[PolicyValidator] = None,
        confidence_calculator: Optional[ConfidenceCalculatorDecision] = None,
        execution_builder: Optional[ExecutionPackageBuilder] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        """Initialize Decision Engine Core with Council sub-components."""
        self.consensus_manager = consensus_manager or ConsensusManager()
        self.scoring_engine = scoring_engine or ScoringEngineDecision()
        self.conflict_resolver = conflict_resolver or ConflictResolver()
        self.approval_router = approval_router or ApprovalRouter()
        self.policy_validator = policy_validator or PolicyValidator()
        self.confidence_calculator = confidence_calculator or ConfidenceCalculatorDecision()
        self.execution_builder = execution_builder or ExecutionPackageBuilder()
        self.audit_logger = audit_logger or AuditLogger()

        logger.info("DecisionEngineCore initialized successfully")

    def evaluate_proposal(
        self,
        target_id: str,
        action: str,
        votes: list[AgentVote],
        estimated_savings_usd: float = 0.0,
        risk_category: str = "LOW",
        region: str = "us-east-1",
        is_production: bool = False,
        compliance_frameworks: list[str] = None,
        current_time: Optional[datetime] = None,
        score_inputs: Optional[dict[str, float]] = None,
    ) -> DecisionRecord:
        """Evaluate a proposal through the Decision Council pipeline.

        Args:
            target_id: Target resource or application
            action: Proposed action (e.g. RESIZE, TERMINATE)
            votes: Vote collection from M1-M8 agents
            estimated_savings_usd: Expected monthly savings
            risk_category: Risk level
            region: Target cloud region
            is_production: Production flag
            compliance_frameworks: Compliance tags
            current_time: Current timestamp
            score_inputs: Component values for scoring (business_value, etc.)

        Returns:
            Fully evaluated DecisionRecord
        """
        decision_id = f"dec-{uuid.uuid4().hex[:10]}"
        now = current_time or datetime.utcnow()

        # 1. Consensus Aggregation
        consensus = self.consensus_manager.aggregate_votes(votes)

        # 2. Confidence Aggregation
        confidence = self.confidence_calculator.calculate(votes)

        # 3. Policy Validation
        policy_report = self.policy_validator.validate(
            target_id=target_id,
            action=action,
            region=region,
            is_production=is_production,
            compliance_frameworks=compliance_frameworks,
            current_time=now,
        )

        # 4. Conflict Resolution & Initial State Determination
        state, conflict_explanation = self.conflict_resolver.resolve(consensus)

        # 5. Scoring
        sc_inputs = score_inputs or {}
        # Policy score is 100 if compliant, 0 if not
        policy_val = 100.0 if policy_report.is_compliant else 0.0
        score = self.scoring_engine.calculate_score(
            business_value=sc_inputs.get("business_value", 50.0),
            risk=sc_inputs.get("risk", 50.0),
            simulation=sc_inputs.get("simulation", 50.0),
            learning=sc_inputs.get("learning", 50.0),
            roi=sc_inputs.get("roi", 50.0),
            policies=policy_val,
            confidence=confidence,
        )

        # 6. Routing Approval levels
        approval_route = self.approval_router.route(
            risk_category=risk_category,
            estimated_savings_usd=estimated_savings_usd,
            has_policy_violations=not policy_report.is_compliant,
        )

        # Determine Final Decision State
        explanation = conflict_explanation
        if not policy_report.is_compliant:
            state = DecisionState.BLOCKED
            explanation = f"Blocked by policies: {', '.join(policy_report.violations)}"
        elif state == DecisionState.APPROVED:
            # If routed to Auto-Execute, auto-approve. Otherwise require approval
            if approval_route.level == ApprovalLevel.AUTO_EXECUTE:
                state = DecisionState.AUTO_APPROVED
                explanation = f"Auto-approved. Level: {approval_route.reason}"
            else:
                state = DecisionState.REQUIRES_APPROVAL
                explanation = f"Requires human approval. Route: {approval_route.reason}"

        # Construct basic DecisionRecord
        record = DecisionRecord(
            decision_id=decision_id,
            target_id=target_id,
            action=action,
            state=state,
            consensus=consensus,
            score=score,
            approval_route=approval_route,
            policy_report=policy_report,
            decision_confidence=confidence,
            explanation=explanation,
            created_at=now,
        )

        # 7. Execution Package Builder (only if approved / auto-approved)
        if state in (DecisionState.APPROVED, DecisionState.AUTO_APPROVED):
            record.execution_package = self.execution_builder.build(record)
            record.decided_at = now

        # 8. Audit Logging
        self.audit_logger.log_decision(record)

        return record
