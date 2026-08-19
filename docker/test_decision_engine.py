"""
test_decision_engine.py

Comprehensive unit and integration test suite for the Decision Engine (M9).
Tests voting, consensus, scoring, conflict resolution, approval routing,
policy validation, confidence calculation, execution package building,
audit logging, overrides, agent orchestrations, and API router.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from models_decision import (
    AgentVote,
    ApprovalLevel,
    DecisionRecord,
    DecisionState,
    OverrideAction,
    OverrideRecord,
    VoteVerdict,
    ConsensusResult,
    ConflictResolutionStrategy,
)
from consensus_manager import ConsensusManager
from scoring_engine_decision import ScoringEngineDecision
from conflict_resolver import ConflictResolver
from approval_router import ApprovalRouter
from policy_validator import PolicyValidator
from confidence_calculator_decision import ConfidenceCalculatorDecision
from execution_package_builder import ExecutionPackageBuilder
from audit_logger import AuditLogger
from override_manager import OverrideManager
from decision_engine_core import DecisionEngineCore
from decision_agent import DecisionAgent
from decision_routes import create_decision_router


# ═══════════════════════════════════════════════════════════════
# Test Fixtures / Helpers
# ═══════════════════════════════════════════════════════════════


def make_vote(agent: str, verdict: VoteVerdict, confidence: float = 90.0, reasoning: str = "") -> AgentVote:
    """Create a mock AgentVote."""
    return AgentVote(
        agent_name=agent,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning or f"Vote from {agent}",
    )


def make_mock_votes_unanimous_approve() -> list[AgentVote]:
    """Create a set of unanimous approve votes."""
    return [
        make_vote("Infrastructure", VoteVerdict.APPROVE, 95.0),
        make_vote("Cost", VoteVerdict.APPROVE, 85.0),
        make_vote("Risk", VoteVerdict.APPROVE, 90.0),
        make_vote("Strategy", VoteVerdict.APPROVE, 92.0),
        make_vote("Learning", VoteVerdict.APPROVE, 88.0),
    ]


def make_mock_votes_split() -> list[AgentVote]:
    """Create a set of split votes."""
    return [
        make_vote("Infrastructure", VoteVerdict.APPROVE, 90.0),
        make_vote("Cost", VoteVerdict.APPROVE, 80.0),
        make_vote("Risk", VoteVerdict.REJECT, 95.0, "Critical performance issue detected"),
        make_vote("Strategy", VoteVerdict.APPROVE, 85.0),
        make_vote("Learning", VoteVerdict.APPROVE, 80.0),
    ]


# ═══════════════════════════════════════════════════════════════
# Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestConsensusManager:
    """Tests Consensus Manager functionality."""

    def test_unanimous_approve(self) -> None:
        manager = ConsensusManager()
        votes = make_mock_votes_unanimous_approve()
        result = manager.aggregate_votes(votes)

        assert result.approve_count == 5
        assert result.reject_count == 0
        assert result.consensus_type == "UNANIMOUS"
        assert result.recommended_action == VoteVerdict.APPROVE

    def test_split_votes(self) -> None:
        manager = ConsensusManager()
        votes = make_mock_votes_split()
        result = manager.aggregate_votes(votes)

        assert result.approve_count == 4
        assert result.reject_count == 1
        assert result.consensus_type == "MAJORITY"
        # Majority is approve, but since reject exists and has_conflict handles it, recommended action is conditional/approve
        assert result.recommended_action == VoteVerdict.APPROVE

    def test_abstain_only(self) -> None:
        manager = ConsensusManager()
        votes = [make_vote("Risk", VoteVerdict.ABSTAIN)]
        result = manager.aggregate_votes(votes)

        assert result.consensus_type == "DEADLOCK"
        assert result.recommended_action == VoteVerdict.ABSTAIN


class TestScoringEngineDecision:
    """Tests Decision Scoring Engine."""

    def test_calculate_score_default_weights(self) -> None:
        engine = ScoringEngineDecision()
        score = engine.calculate_score(
            business_value=80.0,
            risk=90.0,
            simulation=85.0,
            learning=75.0,
            roi=95.0,
            policies=100.0,
            confidence=90.0,
        )

        assert score.overall_score > 0.0
        assert score.overall_score <= 100.0
        assert score.weights_used["business_value"] == 0.25

    def test_calculate_score_custom_weights(self) -> None:
        custom_weights = {"business_value": 0.5, "risk": 0.5}
        engine = ScoringEngineDecision(weights=custom_weights)
        score = engine.calculate_score(business_value=100.0, risk=80.0)

        # 0.5 * 100 + 0.5 * 80 = 90
        assert score.overall_score == 90.0


class TestConflictResolver:
    """Tests Conflict Resolver rules."""

    def test_no_conflict_approved(self) -> None:
        resolver = ConflictResolver()
        consensus = ConsensusResult(
            votes=[], approve_count=3, reject_count=0, recommended_action=VoteVerdict.APPROVE
        )
        state, explanation = resolver.resolve(consensus)

        assert state == DecisionState.APPROVED
        assert "No conflict" in explanation

    def test_conservative_strategy_requires_approval(self) -> None:
        resolver = ConflictResolver(strategy=ConflictResolutionStrategy.CONSERVATIVE)
        votes = make_mock_votes_split()
        consensus = ConsensusResult(
            votes=votes, approve_count=4, reject_count=1, recommended_action=VoteVerdict.CONDITIONAL
        )
        state, explanation = resolver.resolve(consensus)

        assert state == DecisionState.REQUIRES_APPROVAL
        assert "CONSERVATIVE" in explanation

    def test_majority_wins(self) -> None:
        resolver = ConflictResolver()
        votes = make_mock_votes_split()
        consensus = ConsensusResult(
            votes=votes, approve_count=4, reject_count=1, recommended_action=VoteVerdict.CONDITIONAL
        )
        state, explanation = resolver.resolve(consensus, strategy=ConflictResolutionStrategy.MAJORITY_WINS)

        assert state == DecisionState.CONDITIONAL
        assert "MAJORITY_WINS" in explanation


class TestApprovalRouter:
    """Tests Approval routing matrix."""

    def test_auto_execute(self) -> None:
        router = ApprovalRouter()
        route = router.route(risk_category="LOW", estimated_savings_usd=100.0)
        assert route.level == ApprovalLevel.AUTO_EXECUTE

    def test_engineering_approval(self) -> None:
        router = ApprovalRouter()
        route = router.route(risk_category="LOW", estimated_savings_usd=1000.0)
        assert route.level == ApprovalLevel.ENGINEERING_LEAD

    def test_sre_approval(self) -> None:
        router = ApprovalRouter()
        route = router.route(risk_category="MEDIUM", estimated_savings_usd=10000.0)
        assert route.level == ApprovalLevel.SRE_TEAM

    def test_executive_approval(self) -> None:
        router = ApprovalRouter()
        route = router.route(risk_category="HIGH", estimated_savings_usd=50000.0)
        assert route.level == ApprovalLevel.EXECUTIVE_APPROVAL

    def test_policy_violations_routing(self) -> None:
        router = ApprovalRouter()
        route = router.route(risk_category="LOW", estimated_savings_usd=100.0, has_policy_violations=True)
        assert route.level == ApprovalLevel.SECURITY_TEAM


class TestPolicyValidator:
    """Tests Policy Validator checks."""

    def test_policy_valid_normal_hours(self) -> None:
        validator = PolicyValidator(business_hours=(9, 17))
        # 18:00 is outside business hours (9-17) => safe window
        current = datetime(2026, 7, 20, 18, 0, 0)  # Monday
        report = validator.validate(
            target_id="res-1", action="RESIZE", is_production=True, current_time=current
        )
        assert report.is_compliant is True

    def test_policy_invalid_business_hours(self) -> None:
        validator = PolicyValidator(business_hours=(9, 17))
        current = datetime(2026, 7, 20, 10, 0, 0)  # Monday 10:00 AM
        report = validator.validate(
            target_id="res-1", action="TERMINATE", is_production=True, current_time=current
        )
        # Production destructive action during business hours => violation
        assert report.is_compliant is False
        assert any("BUSINESS_HOURS" in v for v in report.violations)

    def test_change_freeze(self) -> None:
        validator = PolicyValidator(change_freeze=True)
        report = validator.validate(target_id="res-1", action="RESIZE")
        assert report.is_compliant is False
        assert any("CHANGE_FREEZE" in v for v in report.violations)


class TestConfidenceCalculatorDecision:
    """Tests Decision Confidence Calculator."""

    def test_calculate_confidence_weighted(self) -> None:
        calc = ConfidenceCalculatorDecision()
        votes = [
            make_vote("Infrastructure", VoteVerdict.APPROVE, 100.0),
            make_vote("Cost", VoteVerdict.APPROVE, 50.0),
        ]
        result = calc.calculate(votes)
        # Self-weighted average of 100 (weight 1.0) and 50 (weight 0.5)
        # Weighted sum: 100*1.0 + 50*0.5 = 125. Total weight: 1.5. 125 / 1.5 = 83.33
        assert result == pytest.approx(83.33, abs=0.01)


class TestExecutionPackageBuilder:
    """Tests Execution Package compilation."""

    def test_build_package(self) -> None:
        builder = ExecutionPackageBuilder()
        decision = DecisionRecord(
            decision_id="dec-123",
            target_id="res-1",
            action="RESIZE",
            state=DecisionState.APPROVED,
            created_at=datetime.utcnow(),
        )
        package = builder.build(decision)

        assert package.decision_id == "dec-123"
        assert package.target_id == "res-1"
        assert len(package.execution_steps) > 0
        assert "strategy" in package.rollback_plan


# ═══════════════════════════════════════════════════════════════
# Integration & Orchestration Tests
# ═══════════════════════════════════════════════════════════════


class TestDecisionAgent:
    """Tests the main orchestrator agent flow."""

    def test_evaluate_and_approve_flow(self) -> None:
        agent = DecisionAgent()
        votes = make_mock_votes_unanimous_approve()

        # Proposal with LOW risk and small savings => AUTO_APPROVED
        record = agent.evaluate(
            target_id="res-1",
            action="RESIZE",
            votes=votes,
            estimated_savings_usd=100.0,
            risk_category="LOW",
            is_production=False,
        )

        assert record.state == DecisionState.AUTO_APPROVED
        assert record.execution_package is not None
        assert record.decision_confidence == pytest.approx(90.13, abs=0.1)

    def test_evaluate_requires_approval_flow(self) -> None:
        agent = DecisionAgent()
        votes = make_mock_votes_unanimous_approve()

        # High savings => REQUIRES_APPROVAL
        record = agent.evaluate(
            target_id="res-1",
            action="RESIZE",
            votes=votes,
            estimated_savings_usd=10000.0,
            risk_category="LOW",
            is_production=False,
        )

        assert record.state == DecisionState.REQUIRES_APPROVAL
        assert record.execution_package is None  # not built until approved

        # Manual Approval
        updated = agent.approve(record.decision_id, approver="alice", reason="Looks safe")
        assert updated.state == DecisionState.APPROVED
        assert updated.execution_package is not None

    def test_manual_reject_flow(self) -> None:
        agent = DecisionAgent()
        votes = make_mock_votes_unanimous_approve()

        record = agent.evaluate(
            target_id="res-1",
            action="RESIZE",
            votes=votes,
            estimated_savings_usd=10000.0,
        )
        assert record.state == DecisionState.REQUIRES_APPROVAL

        updated = agent.reject(record.decision_id, rejecter="bob", reason="Not required")
        assert updated.state == DecisionState.REJECTED

    def test_human_override_modify_flow(self) -> None:
        agent = DecisionAgent()
        votes = make_mock_votes_unanimous_approve()

        record = agent.evaluate(
            target_id="res-1",
            action="RESIZE",
            votes=votes,
            estimated_savings_usd=10000.0,
        )

        updated_record, override_record = agent.apply_override(
            decision_id=record.decision_id,
            action=OverrideAction.MODIFY,
            actor="charlie",
            reason="Change action type",
            modified_properties={"action": "TERMINATE"},
        )

        assert updated_record.action == "TERMINATE"
        assert updated_record.state == DecisionState.CONDITIONAL
        assert override_record.actor == "charlie"


class TestDecisionAPIRoutes:
    """Tests FastAPI router creation and endpoint lists."""

    def test_create_router(self) -> None:
        agent = MagicMock()
        router = create_decision_router(agent=agent)
        assert router is not None

        paths = [r.path for r in router.routes]
        assert "/api/decision/evaluate" in paths
        assert "/api/decision/pending" in paths
        assert "/api/decision/history" in paths
        assert "/api/decision/audit" in paths
        assert "/api/decision/approve" in paths
        assert "/api/decision/reject" in paths
        assert "/api/decision/override" in paths
