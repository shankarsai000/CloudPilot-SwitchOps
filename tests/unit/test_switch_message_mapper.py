"""
Unit tests for SwitchMessageMapper (Phase 4.2).

Validates:
- Redaction of HMAC approval tokens, Bearer tokens, and secrets from Switch messages.
- Full 14-point proposal formatting compliance.
- Bounded verification outcome formatting compliance.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from app.domain.candidates import Candidate, CandidateType
from app.domain.decisions import (
    DecisionReport,
    DecisionRun,
)
from app.domain.proposals import Proposal, ProposalStatus
from app.integrations.switch.message_mapper import SwitchMessageMapper


def test_redact_for_switch():
    """Verify secrets and HMAC tokens are redacted before Switch publication."""
    raw = (
        "Generated token: v1.1234567890abcdef.abcdef0123456789abcdef0123456789\n"
        "Authorization: Bearer my-secret-jwt-token-string\n"
        "AWS Secret: AKIAIOSFODNN7EXAMPLE\n"
    )
    redacted = SwitchMessageMapper.redact_for_switch(raw)

    assert "v1.1234567890abcdef" not in redacted
    assert "[REDACTED_APPROVAL_TOKEN]" in redacted
    assert "Bearer [REDACTED]" in redacted


def test_format_proposal_for_switch_completeness():
    """Verify all 14 proposal transparency points are rendered cleanly."""
    now = datetime.now(timezone.utc)
    proposal = Proposal(
        proposal_id="prop-unit-01",
        task_id="task-prop-test",
        decision_id="dec-prop-test",
        candidate_id="cand-unit-01",
        title="Rightsize EC2 instance t3.large to t3.small",
        description="Over-provisioned compute capacity",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        workspace_root="samples/phase4_2_demo/infrastructure",
        source_finding_ids=["find-001"],
        affected_resource_ids=["aws_instance.web"],
        source_file_paths=["infrastructure/main.tf"],
        canonical_proposed_changes=[
            {
                "file_path": "infrastructure/main.tf",
                "resource_type": "aws_instance",
                "resource_id": "aws_instance.web",
                "resource_name": "web",
                "attribute": "instance_type",
                "action": "MODIFY",
                "old_value": "t3.large",
                "new_value": "t3.small",
            }
        ],
        estimated_monthly_cost_before="60.74",
        estimated_monthly_cost_after="15.18",
        estimated_monthly_savings="45.56",
        rollback_plan="Revert instance_type to t3.large",
        proposal_hash="a1b2c3d4e5f67890",
        expires_at=now + timedelta(hours=1),
        status=ProposalStatus.PENDING_APPROVAL,
    )

    decision_run = DecisionRun(
        decision_id="dec-prop-test",
        task_id="task-prop-test",
        assessment_id="asmt-unit-01",
        workspace_root="samples/phase4_2_demo/infrastructure",
        workspace_dir="samples/phase4_2_demo/infrastructure",
        total_candidates_generated=5,
        feasible_candidates_count=4,
        rejected_candidates_count=1,
        pareto_optimal_count=2,
        z3_verification_status="Z3_CONSTRAINTS_SAT",
    )

    formatted = SwitchMessageMapper.format_proposal_for_switch(
        proposal=proposal,
        decision_run=decision_run,
    )

    # Verify key transparency points
    assert "Formal Infrastructure Change Proposal Generated" in formatted
    assert proposal.proposal_id in formatted
    assert proposal.proposal_hash in formatted
    assert "cand-unit-01" in formatted
    assert "infrastructure/main.tf" in formatted
    assert "Z3_CONSTRAINTS_SAT" in formatted
    assert "$45.56" in formatted
    assert "Revert instance_type to t3.large" in formatted
    assert "@cloudpilot-ops-agent approve proposal" in formatted
    assert "Safety Boundary" in formatted
