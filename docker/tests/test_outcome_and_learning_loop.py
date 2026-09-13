"""
Phase 6: Outcome Verification, Deterministic Rollback, Savings Attribution, & Learning Loop Tests.

Validates:
1. 5-Dimensional Outcome Verification (Cost, Performance, Availability, Risk, Savings)
2. Safety Threshold Breach Detection & Rollback Requirement Flagging
3. Deterministic, Idempotent, Auditable, and Validated Automated Rollback
4. 3-Way Savings Attribution (Predicted, Verified, Annualized)
5. Post-Execution Incident Detection & Automated Emergency Rollback
6. M8 Learning Loop Ingestion (Success, Failure, Rollbacks, Human Overrides, Rejections)
7. Cloud DNA Evolution & Experience Replay
8. Continuous Learning Metrics & Calibration
9. Safety Precedence Guard (Learning CANNOT bypass governance policies)
10. FastAPI Verification & Learning Endpoints
"""

import pytest
from fastapi.testclient import TestClient

from governance.autonomy import AutonomyLevel, get_autonomy_manager
from governance.control_plane import get_safety_control_plane
from governance.emergency import get_emergency_stop_manager
from governance.models import ProposedAction, ReversibilityType
from main import app
from simulator.engine import get_simulator
from verification.attribution import (
    PortfolioSavingsSummary,
    SavingsAttributionEngine,
    get_savings_attribution_engine,
)
from verification.engine import OutcomeVerificationEngine, get_verification_engine
from verification.incident import (
    IncidentSeverity,
    PostExecutionIncidentDetector,
    get_incident_detector,
)
from verification.learning_loop import LearningLoopBridge, get_learning_loop_bridge
from verification.models import (
    ActualOutcome,
    ExpectedOutcome,
    OutcomeReport,
    OutcomeVerdict,
    RollbackPlan,
    RollbackResult,
    SafetyThresholds,
    SavingsAttribution,
)
from verification.rollback import AutomatedRollbackManager, get_rollback_manager


@pytest.fixture(autouse=True)
def setup_environment():
    """Reset simulator, governance, and verification states before each test."""
    sim = get_simulator()
    sim.generate("SaaS", seed=42)

    verif = get_verification_engine()
    verif.clear_all()

    rollback = get_rollback_manager()
    rollback.clear_all()

    attr = get_savings_attribution_engine()
    attr.clear_all()

    incidents = get_incident_detector()
    incidents.clear_all()

    bridge = get_learning_loop_bridge()
    bridge.clear_all()

    gov = get_safety_control_plane()
    gov.autonomy.set_level(AutonomyLevel.L4_LIMITED)
    gov.emergency.reset_all()

    yield


@pytest.fixture
def client():
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════
# 1. 5-Dimensional Outcome Verification & Verdicts
# ═══════════════════════════════════════════════════════════════════

def test_generate_expected_outcome_across_5_dimensions():
    engine = get_verification_engine()
    expected = engine.generate_expected_outcome(
        action_id="act-001",
        target_resource_id="i-test-01",
        target_service="compute-service",
        baseline_monthly_cost_usd=200.0,
        expected_monthly_savings_usd=50.0,
        expected_cpu_utilization_pct=40.0,
        expected_memory_headroom_pct=45.0,
        expected_latency_p99_ms=50.0,
        expected_availability_pct=99.99,
        expected_risk_level="LOW",
    )
    assert expected.action_id == "act-001"
    assert expected.baseline_monthly_cost_usd == 200.0
    assert expected.expected_monthly_cost_usd == 150.0
    assert expected.expected_monthly_savings_usd == 50.0
    assert expected.expected_latency_p99_ms == 50.0
    assert expected.expected_availability_pct == 99.99


def test_outcome_verified_success():
    engine = get_verification_engine()
    expected = engine.generate_expected_outcome(
        action_id="act-002",
        target_resource_id="i-test-02",
        baseline_monthly_cost_usd=100.0,
        expected_monthly_savings_usd=30.0,
        expected_latency_p99_ms=40.0,
        expected_availability_pct=99.99,
    )
    actual = engine.collect_actual_outcome(
        action_id="act-002",
        target_resource_id="i-test-02",
        measured_monthly_cost_usd=70.0,
        measured_savings_usd=30.0,
        measured_cpu_utilization_pct=45.0,
        measured_memory_headroom_pct=40.0,
        measured_latency_p99_ms=41.0,  # <= 5% increase
        measured_availability_pct=99.99,
        measured_risk_level="LOW",
    )
    report = engine.verify_and_generate_report(expected, actual)
    assert report.verdict == OutcomeVerdict.VERIFIED_SUCCESS
    assert report.rollback_required is False
    assert len(report.breached_thresholds) == 0
    assert report.savings_realization_rate == 1.0


def test_outcome_acceptable_deviation():
    engine = get_verification_engine()
    expected = engine.generate_expected_outcome(
        action_id="act-003",
        target_resource_id="i-test-03",
        baseline_monthly_cost_usd=100.0,
        expected_monthly_savings_usd=30.0,
        expected_latency_p99_ms=40.0,
        expected_availability_pct=99.99,
    )
    actual = engine.collect_actual_outcome(
        action_id="act-003",
        target_resource_id="i-test-03",
        measured_monthly_cost_usd=75.0,  # Slight deviation, $25 savings instead of $30
        measured_savings_usd=25.0,
        measured_cpu_utilization_pct=50.0,
        measured_memory_headroom_pct=35.0,
        measured_latency_p99_ms=44.0,  # 10% latency increase (tolerable, threshold is 20%)
        measured_availability_pct=99.99,
    )
    report = engine.verify_and_generate_report(expected, actual)
    assert report.verdict == OutcomeVerdict.ACCEPTABLE_DEVIATION
    assert report.rollback_required is False


def test_threshold_breach_latency_spike():
    engine = get_verification_engine()
    expected = engine.generate_expected_outcome(
        action_id="act-004",
        target_resource_id="i-test-04",
        baseline_monthly_cost_usd=100.0,
        expected_monthly_savings_usd=30.0,
        expected_latency_p99_ms=50.0,
        thresholds=SafetyThresholds(max_latency_increase_pct=20.0),
    )
    actual = engine.collect_actual_outcome(
        action_id="act-004",
        target_resource_id="i-test-04",
        measured_monthly_cost_usd=70.0,
        measured_savings_usd=30.0,
        measured_cpu_utilization_pct=60.0,
        measured_memory_headroom_pct=25.0,
        measured_latency_p99_ms=75.0,  # 50% increase -> breach!
        measured_availability_pct=99.99,
    )
    report = engine.verify_and_generate_report(expected, actual)
    assert report.verdict == OutcomeVerdict.THRESHOLD_BREACH
    assert report.rollback_required is True
    assert any("LATENCY_SPIKE" in b for b in report.breached_thresholds)


def test_threshold_breach_availability_drop():
    engine = get_verification_engine()
    expected = engine.generate_expected_outcome(
        action_id="act-005",
        target_resource_id="i-test-05",
        baseline_monthly_cost_usd=100.0,
        expected_monthly_savings_usd=30.0,
        expected_availability_pct=99.99,
        thresholds=SafetyThresholds(min_availability_pct=99.9),
    )
    actual = engine.collect_actual_outcome(
        action_id="act-005",
        target_resource_id="i-test-05",
        measured_monthly_cost_usd=70.0,
        measured_savings_usd=30.0,
        measured_cpu_utilization_pct=50.0,
        measured_memory_headroom_pct=30.0,
        measured_latency_p99_ms=45.0,
        measured_availability_pct=99.2,  # Dropped below 99.9%
    )
    report = engine.verify_and_generate_report(expected, actual)
    assert report.verdict == OutcomeVerdict.THRESHOLD_BREACH
    assert report.rollback_required is True
    assert any("AVAILABILITY_DROP" in b for b in report.breached_thresholds)


def test_threshold_breach_cpu_starvation():
    engine = get_verification_engine()
    expected = engine.generate_expected_outcome(
        action_id="act-006",
        target_resource_id="i-test-06",
        baseline_monthly_cost_usd=100.0,
        expected_monthly_savings_usd=30.0,
        thresholds=SafetyThresholds(max_cpu_utilization_pct=85.0),
    )
    actual = engine.collect_actual_outcome(
        action_id="act-006",
        target_resource_id="i-test-06",
        measured_monthly_cost_usd=70.0,
        measured_savings_usd=30.0,
        measured_cpu_utilization_pct=92.0,  # 92% > 85% limit
        measured_memory_headroom_pct=10.0,
        measured_latency_p99_ms=45.0,
        measured_availability_pct=99.99,
    )
    report = engine.verify_and_generate_report(expected, actual)
    assert report.verdict == OutcomeVerdict.THRESHOLD_BREACH
    assert report.rollback_required is True
    assert any("CPU_STARVATION" in b for b in report.breached_thresholds)


# ═══════════════════════════════════════════════════════════════════
# 2. Deterministic, Idempotent, Auditable, & Validated Rollback
# ═══════════════════════════════════════════════════════════════════

def test_deterministic_rollback_plan_synthesis():
    rollback_mgr = get_rollback_manager()
    plan = rollback_mgr.generate_rollback_plan(
        action_id="act-rb-01",
        target_resource_id="i-compute-001",
        original_action_type="rightsize_instance",
        original_parameters={"source_type": "m5.2xlarge", "target_type": "m5.large"},
    )
    assert plan.action_id == "act-rb-01"
    assert plan.is_deterministic is True
    assert plan.inverse_action_type == "rightsize_instance"
    assert plan.inverse_parameters["source_type"] == "m5.large"
    assert plan.inverse_parameters["target_type"] == "m5.2xlarge"
    assert plan.inverse_parameters["rollback"] is True


def test_rollback_execution_and_simulator_restoration():
    sim = get_simulator()
    ctx = sim.get_context()
    target = ctx.compute[0]
    orig_type = target.instance_type

    # Mutate instance in simulator
    target.instance_type = "t3.nano"

    rollback_mgr = get_rollback_manager()
    plan = rollback_mgr.generate_rollback_plan(
        action_id="act-rb-02",
        target_resource_id=target.instance_id,
        original_action_type="rightsize_instance",
        original_parameters={"source_type": orig_type, "target_type": "t3.nano"},
    )
    result = rollback_mgr.execute_rollback(plan=plan, reason="Testing simulator restoration")

    assert result.status == "SUCCESS"
    assert result.baseline_restored is True
    assert result.audit_record_id is not None
    assert target.instance_type == orig_type


def test_rollback_idempotency():
    rollback_mgr = get_rollback_manager()
    plan = rollback_mgr.generate_rollback_plan(
        action_id="act-rb-03",
        target_resource_id="i-compute-idemp",
        original_action_type="rightsize_instance",
        original_parameters={"source_type": "c5.xlarge", "target_type": "c5.large"},
    )
    result1 = rollback_mgr.execute_rollback(plan=plan)
    assert result1.status == "SUCCESS"
    assert result1.is_idempotent_replay is False

    # Second execution of the exact same rollback plan
    result2 = rollback_mgr.execute_rollback(plan=plan)
    assert result2.status == "ALREADY_ROLLED_BACK"
    assert result2.is_idempotent_replay is True
    assert result2.rollback_id == result1.rollback_id


def test_rollback_auditability_in_immutable_trail():
    gov = get_safety_control_plane()
    initial_count = gov.audit.count_records()

    rollback_mgr = get_rollback_manager()
    plan = rollback_mgr.generate_rollback_plan(
        action_id="act-rb-04",
        target_resource_id="i-audit-res",
        original_action_type="rightsize_instance",
        original_parameters={"source_type": "r5.large", "target_type": "r5.xlarge"},
    )
    result = rollback_mgr.execute_rollback(plan=plan)

    assert gov.audit.count_records() > initial_count
    records = gov.audit.list_records(limit=1)
    assert len(records) > 0
    latest = records[0]
    assert result.audit_record_id == latest.record_id
    assert "Deterministic Rollback" in latest.objective
    # Verify cryptographic integrity of the chain
    is_valid, msg, _ = gov.audit.verify_integrity()
    assert is_valid is True


# ═══════════════════════════════════════════════════════════════════
# 3. 3-Way Savings Attribution (Predicted, Verified, Annualized)
# ═══════════════════════════════════════════════════════════════════

def test_savings_attribution_three_tier_distinction():
    attr_engine = get_savings_attribution_engine()
    attr = attr_engine.attribute_savings(
        action_id="act-att-01",
        target_resource_id="vol-01",
        predicted_monthly_savings_usd=100.0,
        verified_monthly_savings_usd=90.0,
        target_service="storage",
        confidence_calibration_factor=0.95,
        variance_discount_pct=0.05,
    )
    assert attr.predicted_monthly_savings_usd == 100.0
    assert attr.verified_monthly_savings_usd == 90.0
    assert attr.realization_percentage == 90.0
    # Expected Annualized = 90.0 * 12 * 0.95 * (1 - 0.05) = 1080 * 0.95 * 0.95 = 974.70
    expected_annual = round(90.0 * 12 * 0.95 * 0.95, 2)
    assert attr.annualized_savings_usd == expected_annual


def test_portfolio_savings_summary_aggregation():
    attr_engine = get_savings_attribution_engine()
    attr_engine.attribute_savings("act-p-1", "res-1", 100.0, 100.0)
    attr_engine.attribute_savings("act-p-2", "res-2", 200.0, 150.0)

    summary = attr_engine.get_portfolio_summary()
    assert summary.total_actions_evaluated == 2
    assert summary.total_predicted_monthly_usd == 300.0
    assert summary.total_verified_monthly_usd == 250.0
    assert summary.average_realization_percentage == 87.5  # (100 + 75) / 2
    assert summary.highest_realized_action_id == "act-p-1"
    assert summary.lowest_realized_action_id == "act-p-2"


# ═══════════════════════════════════════════════════════════════════
# 4. Post-Execution Incident Detection & Automated Emergency Rollback
# ═══════════════════════════════════════════════════════════════════

def test_incident_detection_and_emergency_rollback_trigger():
    detector = get_incident_detector()
    verif = get_verification_engine()

    expected = verif.generate_expected_outcome(
        action_id="act-inc-01",
        target_resource_id="i-inc-res",
        baseline_monthly_cost_usd=100.0,
        expected_monthly_savings_usd=20.0,
        expected_latency_p99_ms=50.0,
        expected_availability_pct=99.99,
        thresholds=SafetyThresholds(max_latency_absolute_ms=250.0),
    )
    # Severe latency spike hitting 320ms (> 250ms ceiling)
    actual = verif.collect_actual_outcome(
        action_id="act-inc-01",
        target_resource_id="i-inc-res",
        measured_monthly_cost_usd=80.0,
        measured_savings_usd=20.0,
        measured_cpu_utilization_pct=96.0,  # Starvation
        measured_memory_headroom_pct=5.0,
        measured_latency_p99_ms=320.0,
        measured_availability_pct=98.5,     # Major drop
    )

    incidents = detector.evaluate_telemetry(expected, actual, auto_rollback_on_critical=True)
    assert len(incidents) >= 2
    critical_incidents = [i for i in incidents if i.severity == IncidentSeverity.CRITICAL]
    assert len(critical_incidents) > 0
    assert any(i.triggered_rollback for i in incidents)

    # Confirm rollback was executed
    rollback_result = get_rollback_manager().get_rollback_result("act-inc-01")
    assert rollback_result is not None
    assert rollback_result.status == "SUCCESS"


# ═══════════════════════════════════════════════════════════════════
# 5. M8 Learning Loop Ingestion, Cloud DNA, & Experience Replay
# ═══════════════════════════════════════════════════════════════════

def test_learning_loop_ingest_outcome_success():
    bridge = get_learning_loop_bridge()
    verif = get_verification_engine()

    expected = verif.generate_expected_outcome("act-learn-01", "i-res-01", 100.0, 30.0)
    actual = verif.collect_actual_outcome(
        "act-learn-01", "i-res-01", 70.0, 30.0, 40.0, 45.0, 42.0, 99.99
    )
    report = verif.verify_and_generate_report(expected, actual)

    update = bridge.ingest_outcome(report)
    assert update.action_id == "act-learn-01"
    assert update.event_type == "OPTIMIZATION"
    assert update.outcome_type == "SUCCESS"
    assert update.confidence_delta >= 0.0


def test_learning_loop_ingest_threshold_breach():
    bridge = get_learning_loop_bridge()
    verif = get_verification_engine()

    expected = verif.generate_expected_outcome("act-learn-02", "i-res-02", 100.0, 30.0)
    actual = verif.collect_actual_outcome(
        "act-learn-02", "i-res-02", 70.0, 30.0, 95.0, 5.0, 300.0, 95.0
    )
    report = verif.verify_and_generate_report(expected, actual)

    update = bridge.ingest_outcome(report)
    assert update.action_id == "act-learn-02"
    assert update.event_type == "FAILURE"
    assert update.outcome_type == "FAILURE"


def test_learning_loop_human_override_and_rejection():
    bridge = get_learning_loop_bridge()

    # Ingest human override
    override_update = bridge.ingest_human_override(
        action_id="act-ovr-01",
        target_resource_id="i-res-ovr",
        action="rightsize_instance",
        approver="lead-architect",
        override_reason="Need extra capacity for pending marketing campaign",
    )
    assert override_update.event_type == "MANUAL_OVERRIDE"

    # Ingest rejection
    rejection_update = bridge.ingest_rejection(
        action_id="act-rej-01",
        target_resource_id="i-res-rej",
        action="terminate_idle",
        rejected_by="security-lead",
        rejection_reason="Instance contains audit logging agent",
    )
    assert rejection_update.event_type == "REJECTION"
    assert rejection_update.confidence_delta < 0.0


def test_experience_replay_retrieval():
    bridge = get_learning_loop_bridge()
    verif = get_verification_engine()

    expected = verif.generate_expected_outcome(
        "act-exp-01", "i-res-exp", 120.0, 40.0, target_service="payment-gateway"
    )
    actual = verif.collect_actual_outcome(
        "act-exp-01", "i-res-exp", 80.0, 40.0, 45.0, 40.0, 42.0, 99.99
    )
    report = verif.verify_and_generate_report(expected, actual)
    bridge.ingest_outcome(report)

    # Search experiences for payment-gateway
    experiences = bridge.retrieve_experience_priors(
        {"target_service": "payment-gateway", "environment": "production"}, top_k=3
    )
    assert len(experiences) > 0
    match = experiences[0]
    assert match.action == "payment-gateway"
    assert match.actual_savings_usd == 40.0


def test_continuous_improvement_metrics():
    bridge = get_learning_loop_bridge()
    verif = get_verification_engine()

    exp = verif.generate_expected_outcome("act-met-01", "res-met", 100.0, 50.0)
    act = verif.collect_actual_outcome("act-met-01", "res-met", 50.0, 50.0, 40.0, 40.0, 40.0)
    rep = verif.verify_and_generate_report(exp, act)
    bridge.ingest_outcome(rep)

    metrics = bridge.get_continuous_improvement_metrics()
    assert "savings_prediction_accuracy_pct" in metrics
    assert metrics["savings_prediction_accuracy_pct"] == 100.0
    assert "cloud_dna" in metrics
    assert "deployment_style" in metrics["cloud_dna"]


# ═══════════════════════════════════════════════════════════════════
# 6. Safety Precedence Guard: Learning NEVER Bypasses Safety
# ═══════════════════════════════════════════════════════════════════

def test_safety_precedence_guard_policy_violation_denial():
    """
    CRITICAL: Even if learning has 100% confidence, safety policies
    (e.g., prod database termination, blast radius limits) strictly forbid execution.
    """
    bridge = get_learning_loop_bridge()

    # Proposed illegal action: terminate critical production database
    illegal_action = ProposedAction(
        action_id="act-illegal-01",
        action_type="delete_database",
        target_resource_id="db-prod-master",
        target_service="payments-db",
        environment="production",
        risk_level="CRITICAL",
        is_reversible=False,
        reversibility=ReversibilityType.IRREVERSIBLE,
        cost_impact_monthly_usd=-500.0,
        blast_radius_score=0.9,
    )

    verdict = bridge.verify_governance_authority(illegal_action, evolved_confidence=100.0)

    # Must be strictly denied by governance
    assert verdict["governance_authorized"] is False
    assert verdict["learning_bypassed_safety"] is False
    assert verdict["authoritative_verdict"] == "DENIED_BY_SAFETY_GOVERNANCE"
    assert "DENIED" in verdict["governance_verdict_reason"] or "POLICY" in verdict["governance_verdict_reason"]


def test_safety_precedence_guard_emergency_stop():
    """When emergency stop is engaged, no action can execute regardless of confidence."""
    bridge = get_learning_loop_bridge()
    gov = get_safety_control_plane()

    # Trigger emergency stop for production
    gov.emergency.engage(scope="env:production", reason="Security containment")

    action = ProposedAction(
        action_id="act-stopped-01",
        action_type="rightsize_instance",
        target_resource_id="i-prod-01",
        target_service="frontend",
        environment="production",
    )

    verdict = bridge.verify_governance_authority(action, evolved_confidence=99.9)
    assert verdict["governance_authorized"] is False
    assert "EXECUTION BLOCKED" in verdict["governance_verdict_reason"]
    assert verdict["learning_bypassed_safety"] is False


def test_safety_precedence_guard_autonomy_l0_gate():
    """In L0 (Observe), actions cannot execute even if confidence is 100%."""
    bridge = get_learning_loop_bridge()
    gov = get_safety_control_plane()

    gov.autonomy.set_level(AutonomyLevel.L0_OBSERVE)

    action = ProposedAction(
        action_id="act-l0-01",
        action_type="rightsize_instance",
        target_resource_id="i-test-01",
        target_service="frontend",
        environment="staging",
    )

    verdict = bridge.verify_governance_authority(action, evolved_confidence=100.0)
    assert verdict["governance_authorized"] is False
    assert "DENIED: Autonomy level L0_OBSERVE" in verdict["governance_verdict_reason"]


# ═══════════════════════════════════════════════════════════════════
# 7. FastAPI Verification & Learning Endpoints
# ═══════════════════════════════════════════════════════════════════

def test_api_create_expected_and_verify(client):
    # 1. Create expected outcome
    exp_res = client.post(
        "/api/v1/verification/expected",
        json={
            "action_id": "act-api-01",
            "target_resource_id": "i-api-01",
            "baseline_monthly_cost_usd": 200.0,
            "expected_monthly_savings_usd": 50.0,
            "target_service": "api-service",
            "expected_latency_p99_ms": 40.0,
        },
    )
    assert exp_res.status_code == 200
    assert exp_res.json()["expected_monthly_cost_usd"] == 150.0

    # 2. Verify outcome
    ver_res = client.post(
        "/api/v1/verification/verify",
        json={
            "action_id": "act-api-01",
            "target_resource_id": "i-api-01",
            "measured_monthly_cost_usd": 150.0,
            "measured_savings_usd": 50.0,
            "measured_cpu_utilization_pct": 45.0,
            "measured_memory_headroom_pct": 40.0,
            "measured_latency_p99_ms": 41.0,
            "measured_availability_pct": 99.99,
        },
    )
    assert ver_res.status_code == 200
    report = ver_res.json()
    assert report["verdict"] == "VERIFIED_SUCCESS"
    assert report["rollback_required"] is False

    # 3. Retrieve report by action_id
    get_res = client.get("/api/v1/verification/reports/act-api-01")
    assert get_res.status_code == 200
    assert get_res.json()["action_id"] == "act-api-01"


def test_api_rollback_endpoint(client):
    res = client.post(
        "/api/v1/verification/rollback",
        json={
            "action_id": "act-api-rb",
            "target_resource_id": "i-api-rb-01",
            "original_action_type": "rightsize_instance",
            "original_parameters": {"source_type": "m5.large", "target_type": "m5.small"},
            "reason": "Test API rollback",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["baseline_restored"] is True

    # Check history
    hist = client.get("/api/v1/verification/rollback/history")
    assert hist.status_code == 200
    assert len(hist.json()) >= 1


def test_api_savings_attribution_and_summary(client):
    attr_res = client.post(
        "/api/v1/verification/attribution",
        json={
            "action_id": "act-api-attr",
            "target_resource_id": "vol-api-01",
            "predicted_monthly_savings_usd": 100.0,
            "verified_monthly_savings_usd": 85.0,
            "target_service": "storage-service",
        },
    )
    assert attr_res.status_code == 200
    data = attr_res.json()
    assert data["realization_percentage"] == 85.0
    assert data["annualized_savings_usd"] > 0.0

    # Summary
    sum_res = client.get("/api/v1/verification/attribution/summary")
    assert sum_res.status_code == 200
    assert sum_res.json()["total_actions_evaluated"] >= 1


def test_api_learning_feedback_and_metrics(client):
    fb_res = client.post(
        "/api/v1/verification/learning/feedback",
        json={
            "action_id": "act-api-fb",
            "target_resource_id": "i-fb-01",
            "action": "rightsize_instance",
            "feedback_type": "OVERRIDE",
            "actor": "site-reliability-lead",
            "reason": "Override test via API",
        },
    )
    assert fb_res.status_code == 200
    assert fb_res.json()["event_type"] == "MANUAL_OVERRIDE"

    met_res = client.get("/api/v1/verification/learning/metrics")
    assert met_res.status_code == 200
    assert "savings_prediction_accuracy_pct" in met_res.json()
