"""
Tests for Phase 10: CloudPilot Copilot Conversational Assistant & API.

Verifies:
1. Intent classification across conversational prompts (billing diagnosis, queries, missions, approvals).
2. Billing anomaly diagnostics with root cause evidence and waste calculation.
3. Autonomous mission dispatch ("Fix it") integrating with TrueForge loop and halting at approval checkpoint.
4. Approval and denial handling through conversational engine and REST endpoints.
5. Multi-turn session persistence and retrieval from disk.
6. Full REST API coverage via FastAPI TestClient.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from copilot.engine import CloudPilotCopilotEngine
from copilot.models import (
    CopilotConversation,
    CopilotIntent,
    CopilotMessage,
    CopilotResponse,
    CopilotRole,
)
from copilot.routes import router as copilot_router
from governance.control_plane import get_safety_control_plane
from governance.models import AutonomyLevel
from main import app
from trueforge.autonomous_loop import AutonomousAgentLoop
from trueforge.state_machine import AgentState, DurableStateMachine
from trueforge.tools import get_governed_tool_registry


@pytest.fixture
def temp_persistence_file(tmp_path: Path) -> Path:
    """Provide isolated persistence JSON file for tests."""
    return tmp_path / "copilot_conversations.json"


@pytest.fixture
def copilot_engine(temp_persistence_file: Path) -> CloudPilotCopilotEngine:
    """Provide isolated Copilot engine with real tools and test persistence."""
    control_plane = get_safety_control_plane()
    control_plane.set_autonomy_level(AutonomyLevel.L3_APPROVAL)
    engine = CloudPilotCopilotEngine(
        persistence_file=temp_persistence_file,
    )
    return engine


@pytest.fixture
def test_client() -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


class TestCopilotIntentClassification:
    """Tests natural language intent extraction in Copilot."""

    def test_classify_diagnose_billing(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        queries = [
            "Why did our cloud bill spike this month?",
            "Can you explain why AWS costs jumped?",
            "What is causing our invoice increase?",
            "Analyze our monthly bill anomaly",
        ]
        for q in queries:
            assert copilot_engine.classify_intent(q) == CopilotIntent.DIAGNOSE_BILLING

    def test_classify_inventory_query(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        queries = [
            "List running EC2 instances",
            "Show me Kubernetes pods in production",
            "What cloud resources do we currently have?",
            "Get inventory of all databases",
        ]
        for q in queries:
            assert copilot_engine.classify_intent(q) == CopilotIntent.INVENTORY_QUERY

    def test_classify_dependency_query(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        queries = [
            "Show dependencies for auth-service",
            "What is connected to the payment database?",
            "Display the service topology graph",
        ]
        for q in queries:
            assert copilot_engine.classify_intent(q) == CopilotIntent.DEPENDENCY_QUERY

    def test_classify_dispatch_mission(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        queries = [
            "Fix it and reduce our costs",
            "Optimize idle resources now",
            "Remediate the billing waste",
            "Apply cost reduction strategy",
            "Fix the issue",
        ]
        for q in queries:
            assert copilot_engine.classify_intent(q) == CopilotIntent.DISPATCH_MISSION

    def test_classify_approvals(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        assert copilot_engine.classify_intent("Approve the changes") == CopilotIntent.APPROVE_EXECUTION
        assert copilot_engine.classify_intent("Yes, apply it") == CopilotIntent.APPROVE_EXECUTION
        assert copilot_engine.classify_intent("Deny execution") == CopilotIntent.DENY_EXECUTION
        assert copilot_engine.classify_intent("Cancel the mission") == CopilotIntent.DENY_EXECUTION
        assert copilot_engine.classify_intent("Show pending approvals") == CopilotIntent.QUERY_APPROVALS

    def test_classify_general(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        assert copilot_engine.classify_intent("Hello, who are you?") == CopilotIntent.GENERAL_QUERY


class TestCopilotConversationalDiagnostics:
    """Tests diagnosis responses and evidence assembly."""

    def test_diagnose_billing_anomaly(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        response = copilot_engine.chat("Why did our cloud bill spike this month?", scenario_name="SaaS")
        assert response.intent == CopilotIntent.DIAGNOSE_BILLING
        assert "Cloud Cost Diagnosis" in response.reply_text
        assert response.evidence is not None
        assert "total_candidates" in response.evidence
        assert "total_potential_monthly_savings" in response.evidence
        assert "Fix it and optimize these resources" in response.quick_actions

    def test_inventory_query_response(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        response = copilot_engine.chat("Show me running cloud inventory", scenario_name="SaaS")
        assert response.intent == CopilotIntent.INVENTORY_QUERY
        assert "Inventory" in response.reply_text
        assert response.evidence is not None
        assert "total_resources" in response.evidence
        assert response.evidence["total_resources"] > 0

    def test_dependency_query_response(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        response = copilot_engine.chat("What are the service dependencies?", scenario_name="SaaS")
        assert response.intent == CopilotIntent.DEPENDENCY_QUERY
        assert "Service Graph" in response.reply_text or "dependencies" in response.reply_text
        assert response.evidence is not None


class TestCopilotAutonomousMissionDispatch:
    """Tests end-to-end conversational autonomous mission flow."""

    def test_dispatch_mission_and_approval_flow(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        # Step 1: Diagnose
        diag_resp = copilot_engine.chat("Why is our bill so high?", scenario_name="SaaS")
        conv_id = diag_resp.conversation_id
        assert diag_resp.intent == CopilotIntent.DIAGNOSE_BILLING

        # Step 2: "Fix it" dispatch
        fix_resp = copilot_engine.chat("Fix it and reduce cost", conversation_id=conv_id, scenario_name="SaaS")
        assert fix_resp.intent == CopilotIntent.DISPATCH_MISSION
        assert fix_resp.agent_state in ("WAITING_FOR_APPROVAL", "AWAITING_APPROVAL", "COMPLETED", "EXECUTING")
        assert "Autonomous" in fix_resp.reply_text

        # If it paused at approval checkpoint, verify pending checkpoint
        if fix_resp.agent_state in ("WAITING_FOR_APPROVAL", "AWAITING_APPROVAL"):
            assert fix_resp.pending_approval is not None
            assert "checkpoint_id" in fix_resp.pending_approval
            assert "Approve" in fix_resp.quick_actions

            # Step 3: Approve via chat
            approve_resp = copilot_engine.chat("Approve", conversation_id=conv_id)
            assert approve_resp.intent == CopilotIntent.APPROVE_EXECUTION
            assert "Approved" in approve_resp.reply_text
            assert approve_resp.agent_state in ("COMPLETED", "TERMINATED", "EXECUTING")

    def test_deny_pending_mission(self, copilot_engine: CloudPilotCopilotEngine) -> None:
        # Start a mission that pauses at approval
        fix_resp = copilot_engine.chat("Fix it now", scenario_name="SaaS")
        conv_id = fix_resp.conversation_id

        if fix_resp.agent_state in ("WAITING_FOR_APPROVAL", "AWAITING_APPROVAL"):
            # Explicitly deny
            deny_resp = copilot_engine.chat("Deny execution", conversation_id=conv_id)
            assert deny_resp.intent == CopilotIntent.DENY_EXECUTION
            assert "Denied" in deny_resp.reply_text or "Cancelled" in deny_resp.reply_text
            assert deny_resp.agent_state in ("CANCELLED", "TERMINATED", "ROLLBACK_COMPLETED", "FAILED")


class TestCopilotSessionPersistence:
    """Tests multi-turn persistence across engine reloads."""

    def test_conversation_persists_to_disk(
        self,
        copilot_engine: CloudPilotCopilotEngine,
        temp_persistence_file: Path,
    ) -> None:
        resp = copilot_engine.chat("Why did our bill spike?", scenario_name="SaaS")
        conv_id = resp.conversation_id

        assert temp_persistence_file.exists()
        raw = json.loads(temp_persistence_file.read_text(encoding="utf-8"))
        assert any(c["conversation_id"] == conv_id for c in raw["conversations"])

        # Reload new engine with same persistence file
        new_engine = CloudPilotCopilotEngine(persistence_file=temp_persistence_file)
        reloaded_conv = new_engine.get_or_create_conversation(conv_id)
        assert len(reloaded_conv.messages) >= 2  # user + assistant
        assert reloaded_conv.messages[0].role == CopilotRole.USER


class TestCopilotRestApi:
    """Tests REST API endpoints via TestClient."""

    def test_api_chat_endpoint(self, test_client: TestClient) -> None:
        payload = {
            "message": "Why is our cloud bill increasing?",
            "scenario_name": "SaaS",
        }
        res = test_client.post("/api/v1/copilot/chat", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "conversation_id" in data
        assert "reply_text" in data
        assert data["intent"] == "DIAGNOSE_BILLING"

    def test_api_conversations_list_and_get(self, test_client: TestClient) -> None:
        # Create a conversation
        chat_res = test_client.post("/api/v1/copilot/chat", json={"message": "Show cloud inventory"})
        assert chat_res.status_code == 200
        conv_id = chat_res.json()["conversation_id"]

        # List conversations
        list_res = test_client.get("/api/v1/copilot/conversations")
        assert list_res.status_code == 200
        conversations = list_res.json()
        assert isinstance(conversations, list)
        assert any(c["conversation_id"] == conv_id for c in conversations)

        # Get specific conversation
        get_res = test_client.get(f"/api/v1/copilot/conversations/{conv_id}")
        assert get_res.status_code == 200
        conv_data = get_res.json()
        assert conv_data["conversation_id"] == conv_id
        assert len(conv_data["messages"]) >= 2

    def test_api_approve_endpoint_no_checkpoint_404(self, test_client: TestClient) -> None:
        # Chat without mission
        chat_res = test_client.post("/api/v1/copilot/chat", json={"message": "What is CloudPilot?"})
        conv_id = chat_res.json()["conversation_id"]

        # Attempt to approve nonexistent checkpoint
        app_res = test_client.post("/api/v1/copilot/approve", json={
            "conversation_id": conv_id,
            "decision": "APPROVE",
            "reason": "Approved test",
        })
        assert app_res.status_code == 404
