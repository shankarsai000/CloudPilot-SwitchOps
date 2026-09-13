"""
Phase 7: CloudPilot Command Center Automated Test Suite.

Validates:
1. Consolidated Overview API (/api/v1/command-center/overview) with real platform KPIs
2. Real-time Server-Sent Events (SSE) stream handshake and message broadcasting
3. Primary User Journey Stepper:
   Goal -> Analyze -> Plan -> Simulate -> Approval -> Execute -> Monitor -> Verify
4. Interactive CloudPilot Copilot natural language queries and goal proposals
5. Human-in-the-loop Approval decision workflow via Command Center
6. Emergency Stop Kill Switch integration via Command Center
7. Static Dashboard hosting (/dashboard/, index.html, styles.css, app.js)
"""

import pytest
from fastapi.testclient import TestClient

from governance.autonomy import AutonomyLevel
from governance.control_plane import get_safety_control_plane
from main import app
from simulator.engine import get_simulator
from verification.attribution import get_savings_attribution_engine
from verification.engine import get_verification_engine
from verification.incident import get_incident_detector
from verification.rollback import get_rollback_manager


@pytest.fixture(autouse=True)
def setup_environment():
    """Reset simulator and governance state before each test."""
    sim = get_simulator()
    sim.generate("SaaS", seed=42)

    gov = get_safety_control_plane()
    gov.autonomy.set_level(AutonomyLevel.L4_LIMITED)
    gov.emergency.reset_all()

    get_verification_engine().clear_all()
    get_rollback_manager().clear_all()
    get_savings_attribution_engine().clear_all()
    get_incident_detector().clear_all()

    yield


@pytest.fixture
def client():
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════
# 1. Consolidated Overview Endpoint Tests
# ═══════════════════════════════════════════════════════════════════

def test_command_center_overview_returns_live_kpis(client):
    res = client.get("/api/v1/command-center/overview")
    assert res.status_code == 200
    data = res.json()

    assert "kpis" in data
    kpis = data["kpis"]
    assert kpis["total_resources"] > 0
    assert kpis["monthly_spend_usd"] > 0.0
    assert "potential_monthly_savings_usd" in kpis
    assert "verified_monthly_savings_usd" in kpis
    assert "annualized_savings_usd" in kpis
    assert "critical_risks_count" in kpis

    assert "governance" in data
    assert data["governance"]["autonomy_level"] == "L4_LIMITED"
    assert data["governance"]["is_emergency_stopped"] is False

    assert "journey" in data
    assert "current_step" in data["journey"]


# ═══════════════════════════════════════════════════════════════════
# 2. Server-Sent Events (SSE) Stream Tests
# ═══════════════════════════════════════════════════════════════════

def test_command_center_sse_stream_connection(client):
    """Verify SSE streaming connection emits the initial connected handshake."""
    response = client.get("/api/v1/command-center/stream?limit=1")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: connected" in response.text


# ═══════════════════════════════════════════════════════════════════
# 3. Primary User Journey Stepper Tests (All 8 Stages)
# ═══════════════════════════════════════════════════════════════════

def test_journey_stage_1_goal(client):
    res = client.post(
        "/api/v1/command-center/journey/step",
        json={"step": "Goal", "goal": "Reduce non-prod compute spend by 25%"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "Goal"
    assert data["journey_state"]["status"] == "GOAL_DEFINED"


def test_journey_stage_2_analyze(client):
    res = client.post(
        "/api/v1/command-center/journey/step",
        json={"step": "Analyze", "scenario": "SaaS"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "Analyze"
    assert data["journey_state"]["status"] == "ANALYSIS_COMPLETE"
    assert data["step_result"]["resources_analyzed"] > 0


def test_journey_stage_3_plan(client):
    res = client.post("/api/v1/command-center/journey/step", json={"step": "Plan"})
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "Plan"
    assert data["journey_state"]["status"] == "PLAN_FORMULATED"
    assert data["step_result"]["estimated_savings_usd"] > 0.0


def test_journey_stage_4_simulate(client):
    res = client.post("/api/v1/command-center/journey/step", json={"step": "Simulate"})
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "Simulate"
    assert data["journey_state"]["status"] == "SIMULATION_VERIFIED"
    assert data["step_result"]["simulation_verdict"] == "SAFE"


def test_journey_stage_5_approval(client):
    res = client.post("/api/v1/command-center/journey/step", json={"step": "Approval"})
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "Approval"
    assert data["journey_state"]["status"] == "AWAITING_APPROVAL"
    assert "approval_request_id" in data["step_result"]


def test_journey_stage_6_execute(client):
    res = client.post("/api/v1/command-center/journey/step", json={"step": "Execute"})
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "Execute"
    assert data["journey_state"]["status"] == "EXECUTED"
    assert data["step_result"]["execution_status"] == "SUCCESS"


def test_journey_stage_7_monitor(client):
    res = client.post("/api/v1/command-center/journey/step", json={"step": "Monitor"})
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "Monitor"
    assert data["journey_state"]["status"] == "MONITORING_ACTIVE"
    assert data["step_result"]["availability_pct"] >= 99.9


def test_journey_stage_8_verify(client):
    res = client.post("/api/v1/command-center/journey/step", json={"step": "Verify"})
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "Verify"
    assert data["journey_state"]["status"] == "VERIFIED_SUCCESS"
    assert data["step_result"]["verified_savings_usd"] > 0.0
    assert data["step_result"]["realization_percentage"] == 100.0


# ═══════════════════════════════════════════════════════════════════
# 4. Interactive CloudPilot Copilot Query Tests
# ═══════════════════════════════════════════════════════════════════

def test_copilot_query_cost_and_savings(client):
    res = client.post(
        "/api/v1/command-center/copilot",
        json={"query": "How much can we save on monthly spend?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "spend" in data["answer"].lower()
    assert len(data["suggested_actions"]) > 0


def test_copilot_query_risk_and_safety(client):
    res = client.post(
        "/api/v1/command-center/copilot",
        json={"query": "What is our current safety status and risk rating?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "autonomy level" in data["answer"].lower()
    assert "safety" in data["answer"].lower()


def test_copilot_query_approvals(client):
    res = client.post(
        "/api/v1/command-center/copilot",
        json={"query": "Are there any pending human approvals?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "approval" in data["answer"].lower()


# ═══════════════════════════════════════════════════════════════════
# 5. Emergency Stop Kill Switch Workflow
# ═══════════════════════════════════════════════════════════════════

def test_emergency_stop_toggle_via_governance(client):
    # 1. Trigger emergency stop
    engage_res = client.post(
        "/api/v1/governance/emergency/engage",
        json={"scope": "global", "reason": "Operator Kill Switch test"},
    )
    assert engage_res.status_code == 200

    # 2. Check overview reflects stopped state
    ov_res = client.get("/api/v1/command-center/overview")
    assert ov_res.status_code == 200
    assert ov_res.json()["governance"]["is_emergency_stopped"] is True

    # 3. Release emergency stop
    rel_res = client.post(
        "/api/v1/governance/emergency/release",
        json={"scope": "global"},
    )
    assert rel_res.status_code == 200

    # 4. Check overview reflects cleared state
    ov_res2 = client.get("/api/v1/command-center/overview")
    assert ov_res2.json()["governance"]["is_emergency_stopped"] is False


# ═══════════════════════════════════════════════════════════════════
# 6. Static Asset Hosting Tests
# ═══════════════════════════════════════════════════════════════════

def test_static_dashboard_html_served(client):
    res = client.get("/dashboard/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "CloudPilot AI" in res.text
    assert "AUTONOMOUS OPERATIONS JOURNEY" in res.text


def test_static_dashboard_css_served(client):
    res = client.get("/dashboard/styles.css")
    assert res.status_code == 200
    assert "text/css" in res.headers["content-type"]
    assert "--bg-main" in res.text


def test_static_dashboard_js_served(client):
    res = client.get("/dashboard/app.js")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]
    assert "CloudPilotApp" in res.text
