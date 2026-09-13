"""
Phase 4 Integration Tests: TrueForge Autonomous Agent Runtime.

Validates the complete 10-step agent loop, controlled MCP tools, sandbox isolation,
audit logging, state persistence, approval interrupts, and REST APIs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List
import pytest
from fastapi.testclient import TestClient

from trueforge.gateway import TrueForgeGatewayAdapter, build_cloudpilot_agent_manifest
from trueforge.models import (
    ApprovalAllow,
    ApprovalDeny,
    ExecutionPlan,
    ModelMessageDeltaEvent,
    ModelMessageEvent,
    OperationalObjective,
    SandboxCreatedEvent,
    Session,
    ToolApprovalRequiredEvent,
    ToolResponseEvent,
    Turn,
    TurnCreatedEvent,
    TurnDoneEvent,
    TurnStateCancelled,
    TurnStateDone,
    TurnStateError,
    UserMessage,
    UserToolApprovalEvent,
    is_event_delta,
    merge_event_delta,
)
from trueforge.runtime import TrueForgeAgentRuntime, get_agent_runtime
from trueforge.sandbox import SandboxManager, SandboxSecurityViolation, get_sandbox_manager
from trueforge.state import AgentStateManager, get_agent_state_manager
from trueforge.tools import ControlledToolRegistry, get_tool_registry


# -----------------------------------------------------------------------------
# Test Suite 1: Manifest & Tool Declarations
# -----------------------------------------------------------------------------
class TestTrueForgeManifestAndTools:
    """Validate official TrueForge AgentManifest and controlled MCP tools."""

    def test_agent_manifest_structure(self) -> None:
        manifest = build_cloudpilot_agent_manifest()
        assert manifest.name == "cloudpilot-cost-optimizer"
        assert manifest.model.name is not None
        assert len(manifest.mcp_servers) > 0
        assert manifest.config.sandbox.enabled is True
        assert manifest.config.sandbox.file_downloads is True

    def test_controlled_tool_registry(self) -> None:
        registry = ControlledToolRegistry()
        tools = registry.list_tools()
        tool_names = [t["function"]["name"] for t in tools]

        expected_tools = [
            "inspect_infrastructure",
            "analyze_costs",
            "inspect_dependencies",
            "analyze_risks",
            "simulate_action",
            "generate_terraform",
            "execute_terraform_plan",
            "execute_sandbox_code",
            "inspect_resource_state",
        ]
        for exp in expected_tools:
            assert exp in tool_names, f"Expected controlled tool {exp} not registered"

    def test_tool_execution_and_audit_logging(self) -> None:
        registry = ControlledToolRegistry()
        res = registry.execute_tool(
            tool_name="inspect_infrastructure",
            arguments={"scenario_name": "SaaS"},
            tool_call_id="call-test-101",
            turn_id="turn-test-101",
        )
        assert res["scenario_name"] == "SaaS"
        assert res["total_resources"] > 0

        logs = registry.get_audit_logs(turn_id="turn-test-101")
        assert len(logs) == 1
        assert logs[0].tool_name == "inspect_infrastructure"
        assert logs[0].status == "SUCCESS"
        assert logs[0].duration_ms > 0

    def test_cost_analysis_and_waste_identification(self) -> None:
        registry = ControlledToolRegistry()
        cost_res = registry.execute_tool(
            tool_name="analyze_costs",
            arguments={"scenario_name": "SaaS", "target_reduction_pct": 20.0},
        )
        assert cost_res["total_monthly_spend_usd"] > 0
        assert cost_res["target_savings_usd"] > 0
        assert len(cost_res["candidates"]) > 0

    def test_dependency_inspection_critical_tier_mapping(self) -> None:
        registry = ControlledToolRegistry()
        dep_res = registry.execute_tool(
            tool_name="inspect_dependencies",
            arguments={"scenario_name": "SaaS"},
        )
        apps = dep_res["applications"]
        assert len(apps) > 0
        critical_apps = [a for a in apps if a["is_critical"]]
        assert len(critical_apps) > 0
        assert all(a["criticality_tier"] in ("tier-1", "tier-2") for a in critical_apps)

    def test_risk_analysis_protects_critical_apps(self) -> None:
        registry = ControlledToolRegistry()

        # Action targeting dev compute -> SAFE
        safe_action = [
            {"target_resource_id": "dev-instance-1", "target_service": "dev-batch", "environment": "dev"}
        ]
        res_safe = registry.execute_tool("analyze_risks", {"proposed_actions": safe_action})
        assert res_safe["any_critical_app_violation"] is False
        assert res_safe["safe_to_proceed_with_approval"] is True

        # Action targeting payment-service or production -> VIOLATION
        unsafe_action = [
            {"target_resource_id": "prod-db-1", "target_service": "payment-service", "environment": "prod"}
        ]
        res_unsafe = registry.execute_tool("analyze_risks", {"proposed_actions": unsafe_action})
        assert res_unsafe["any_critical_app_violation"] is True
        assert res_unsafe["overall_risk_level"] == "CRITICAL_VIOLATION"


# -----------------------------------------------------------------------------
# Test Suite 2: Sandbox Isolation & Safety
# -----------------------------------------------------------------------------
class TestSandboxIsolationAndExecution:
    """Validate sandbox directory isolation, timeouts, output capture, and artifact storage."""

    def test_sandbox_lifecycle_and_dir_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sbx = SandboxManager(base_dir=Path(tmp_dir))
            sid = sbx.create_sandbox()
            path = sbx.get_sandbox_path(sid)
            assert path.exists()
            assert (path / "artifacts").exists()

            # Cleanup
            sbx.cleanup_sandbox(sid)
            assert not path.exists()

    def test_sandbox_command_execution_and_output_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sbx = SandboxManager(base_dir=Path(tmp_dir))
            sid = sbx.create_sandbox()

            res = sbx.execute_command(
                sandbox_id=sid,
                command=["python", "-c", "print('hello from sandbox')"],
            )
            assert res.exit_code == 0
            assert "hello from sandbox" in res.stdout
            assert res.timed_out is False

    def test_sandbox_timeout_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sbx = SandboxManager(base_dir=Path(tmp_dir), default_timeout_seconds=1.0)
            sid = sbx.create_sandbox()

            res = sbx.execute_command(
                sandbox_id=sid,
                command=["python", "-c", "import time; time.sleep(3)"],
                timeout_seconds=1.0,
            )
            assert res.timed_out is True
            assert res.exit_code == -1
            assert "timeout" in res.stderr.lower()

    def test_sandbox_security_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sbx = SandboxManager(base_dir=Path(tmp_dir))
            sid = sbx.create_sandbox()

            with pytest.raises(SandboxSecurityViolation):
                sbx.execute_command(sandbox_id=sid, command=["rm -rf /"])

    def test_sandbox_artifact_storage_and_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sbx = SandboxManager(base_dir=Path(tmp_dir))
            sid = sbx.create_sandbox()

            content = "resource \"aws_instance\" \"test\" {}\n"
            artifact = sbx.store_artifact(
                sandbox_id=sid,
                filename="test.tf",
                content=content,
                artifact_type="terraform_hcl",
            )
            assert artifact.size_bytes == len(content.encode("utf-8"))
            assert len(artifact.sha256_hash) == 64

            # Download using get_sandbox_file
            fetched = sbx.get_sandbox_file(sid, artifact.relative_path)
            assert fetched.decode("utf-8").replace("\r\n", "\n") == content

            # Verify path traversal prevention
            with pytest.raises(PermissionError):
                sbx.get_sandbox_file(sid, "../../etc/passwd")

    def test_sandbox_terraform_plan_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sbx = SandboxManager(base_dir=Path(tmp_dir))
            sid = sbx.create_sandbox()

            hcl = (
                'resource "aws_instance" "dev_worker_1" {\n'
                '  instance_type = "t3.small"\n'
                '  # action: rightsize\n'
                '}\n'
            )
            plan_res = sbx.execute_terraform_plan(sandbox_id=sid, hcl_code=hcl)
            assert plan_res["status"] == "SUCCESS"
            assert plan_res["resources_changed"] >= 1
            assert "execution plan" in plan_res["plan_output"].lower()


# -----------------------------------------------------------------------------
# Test Suite 3: 10-Step Autonomous Agent Lifecycle
# -----------------------------------------------------------------------------
class TestTrueForgeAutonomousLifecycle:
    """End-to-end testing of the 10-step autonomous agent lifecycle."""

    def test_full_autonomous_objective_turn_1_pauses_for_approval(self) -> None:
        runtime = get_agent_runtime()
        session = runtime.create_session(title="Cost Optimization Run")

        # Turn 1: Submit natural-language objective
        prompt = "Reduce monthly cloud cost by 20% without affecting critical applications."
        events = list(runtime.create_turn_stream(
            session_id=session.id,
            input_items=[UserMessage(content=prompt)],
        ))

        event_types = [type(e).__name__ for e in events]
        assert "TurnCreatedEvent" in event_types
        assert "SandboxCreatedEvent" in event_types
        assert "McpInitializeEvent" in event_types
        assert "ToolResponseEvent" in event_types
        assert "ModelMessageEvent" in event_types
        assert "ToolApprovalRequiredEvent" in event_types
        assert "TurnDoneEvent" in event_types

        # Inspect Turn 1 terminal state
        turn_done = next(e for e in events if isinstance(e, TurnDoneEvent))
        term_state = turn_done.state
        assert isinstance(term_state, TurnStateDone)
        assert term_state.status == "done"
        assert term_state.output is None  # Paused turn: output is None
        assert len(term_state.required_actions) == 1
        assert isinstance(term_state.required_actions[0], ToolApprovalRequiredEvent)

        # Inspect approval required event
        app_req = term_state.required_actions[0]
        assert len(app_req.tool_calls) > 0
        pending_tool_call_id = app_req.tool_calls[0].id

        # Verify checkpoint was stored
        turn_created = next(e for e in events if isinstance(e, TurnCreatedEvent))
        turn_id = turn_created.turn_id
        checkpoint = runtime.state.get_checkpoint(turn_id)
        assert checkpoint is not None
        plan_data = checkpoint["execution_plan"]
        assert plan_data["projected_cost_reduction_pct"] >= 19.9
        # Verify critical applications are protected
        assert len(plan_data["critical_applications_protected"]) > 0

    def test_approval_resumption_allow(self) -> None:
        runtime = get_agent_runtime()
        session = runtime.create_session(title="Approval Allow Run")

        # Turn 1
        prompt = "Reduce monthly cloud cost by 20% without affecting critical applications."
        turn_1 = runtime.create_turn(
            session_id=session.id,
            input_items=[UserMessage(content=prompt)],
        )
        assert len(turn_1.state.required_actions) > 0
        gated_call_id = turn_1.state.required_actions[0].tool_calls[0].id

        # Turn 2: Resume with UserToolApprovalEvent(ApprovalAllow())
        approval_event = UserToolApprovalEvent(
            thread_id="main",
            tool_call_id=gated_call_id,
            approval=ApprovalAllow(),
        )
        events_t2 = list(runtime.create_turn_stream(
            session_id=session.id,
            input_items=[approval_event],
            previous_turn_id=turn_1.id,
        ))

        # Check that tool.response was emitted for the gated tool
        tool_resps = [e for e in events_t2 if isinstance(e, ToolResponseEvent)]
        assert any(tr.tool_call_id == gated_call_id for tr in tool_resps)

        # Check that final model.message confirms application
        turn_done_2 = next(e for e in events_t2 if isinstance(e, TurnDoneEvent))
        state_2 = turn_done_2.state
        assert isinstance(state_2, TurnStateDone)
        assert state_2.output is not None
        assert "Successfully Applied" in state_2.output.content
        assert len(state_2.required_actions) == 0

    def test_approval_resumption_deny(self) -> None:
        runtime = get_agent_runtime()
        session = runtime.create_session(title="Approval Deny Run")

        # Turn 1
        prompt = "Reduce monthly cloud cost by 20% without affecting critical applications."
        turn_1 = runtime.create_turn(
            session_id=session.id,
            input_items=[UserMessage(content=prompt)],
        )
        gated_call_id = turn_1.state.required_actions[0].tool_calls[0].id

        # Turn 2: Resume with UserToolApprovalEvent(ApprovalDeny())
        deny_event = UserToolApprovalEvent(
            thread_id="main",
            tool_call_id=gated_call_id,
            approval=ApprovalDeny(reason="Budget freeze in effect"),
        )
        events_t2 = list(runtime.create_turn_stream(
            session_id=session.id,
            input_items=[deny_event],
            previous_turn_id=turn_1.id,
        ))

        turn_done_2 = next(e for e in events_t2 if isinstance(e, TurnDoneEvent))
        state_2 = turn_done_2.state
        assert isinstance(state_2, TurnStateDone)
        assert state_2.output is not None
        assert "Aborted" in state_2.output.content or "Denied" in state_2.output.content

    def test_streaming_event_deltas_merge_correctly(self) -> None:
        runtime = get_agent_runtime()
        session = runtime.create_session(title="Delta Merge Run")

        events = list(runtime.create_turn_stream(
            session_id=session.id,
            input_items=[UserMessage(content="Reduce monthly cloud cost by 20%")],
        ))

        # Reconstruct deltas using official helper functions
        event_map: Dict[str, Any] = {}
        for ev in events:
            if is_event_delta(ev):
                base = event_map.get(ev.id)
                if base:
                    merge_event_delta(base, ev)
            else:
                event_map[ev.id] = ev

        # Verify reconstructed ModelMessageEvent
        model_msgs = [e for e in event_map.values() if isinstance(e, ModelMessageEvent)]
        assert len(model_msgs) > 0
        assert len(model_msgs[0].content) > 50


# -----------------------------------------------------------------------------
# Test Suite 4: State Persistence & Resumability
# -----------------------------------------------------------------------------
class TestStatePersistenceAndRecovery:
    """Verify session, turn, event, and checkpoint disk persistence and recovery."""

    def test_state_persistence_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "state.json"
            mgr1 = AgentStateManager(state_file=state_file)

            s1 = mgr1.create_session(agent_name="cloudpilot-cost-optimizer", title="Persistent Session")
            t1 = mgr1.create_turn(session_id=s1.id, input_items=[UserMessage(content="Hello")])

            plan = ExecutionPlan(
                objective="Save cost",
                scenario_name="SaaS",
                total_baseline_cost_usd=5000.0,
                projected_monthly_savings_usd=1000.0,
                projected_cost_reduction_pct=20.0,
                steps=[],
                critical_applications_protected=["auth-service"],
            )
            mgr1.save_checkpoint(
                session_id=s1.id,
                turn_id=t1.id,
                execution_plan=plan,
                sandbox_id="sbx-test",
                pending_tool_call_ids=["call-1"],
            )

            # Re-instantiate a new manager on the same file
            mgr2 = AgentStateManager(state_file=state_file)
            s_loaded = mgr2.get_session(s1.id)
            assert s_loaded is not None
            assert s_loaded.title == "Persistent Session"

            cp_loaded = mgr2.get_checkpoint(t1.id)
            assert cp_loaded is not None
            assert cp_loaded["sandbox_id"] == "sbx-test"
            assert cp_loaded["execution_plan"]["projected_cost_reduction_pct"] == 20.0

    def test_session_cancellation(self) -> None:
        mgr = AgentStateManager()
        sess = mgr.create_session(title="Cancel Test")
        turn = mgr.create_turn(session_id=sess.id)

        cancelled = mgr.cancel_session(sess.id)
        assert cancelled is True

        turn_updated = mgr.get_turn(sess.id, turn.id)
        assert turn_updated.state.status == "cancelled"


# -----------------------------------------------------------------------------
# Test Suite 5: REST API Integration
# -----------------------------------------------------------------------------
class TestTrueForgeRESTAPIs:
    """Verify FastAPI routes matching TrueFoundry OpenAPI specifications."""

    @pytest.fixture
    def client(self) -> TestClient:
        from main import app
        return TestClient(app)

    def test_api_manifest(self, client: TestClient) -> None:
        resp = client.get("/v1/agents/manifest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "cloudpilot-cost-optimizer"

    def test_api_session_lifecycle(self, client: TestClient) -> None:
        # Create session
        create_resp = client.post("/v1/agents/sessions", json={"title": "REST API Test Session"})
        assert create_resp.status_code == 200
        session_data = create_resp.json()["data"]
        session_id = session_data["id"]
        assert session_id.startswith("sess-")

        # Get session
        get_resp = client.get(f"/v1/agents/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["id"] == session_id

        # List sessions
        list_resp = client.get("/v1/agents/sessions")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["data"]) > 0

    def test_api_create_turn_and_stream(self, client: TestClient) -> None:
        # Create session
        sess_resp = client.post("/v1/agents/sessions", json={"title": "Turn Streaming API Test"})
        session_id = sess_resp.json()["data"]["id"]

        # Turn Stream
        stream_resp = client.post(
            f"/v1/agents/sessions/{session_id}/turns/stream",
            json={"input": [{"type": "user.message", "content": "Reduce cost by 20%"}]},
        )
        assert stream_resp.status_code == 200
        assert "text/event-stream" in stream_resp.headers["content-type"]
        body_text = stream_resp.text
        assert "event: turn.created" in body_text
        assert "event: turn.done" in body_text

    def test_api_convenience_objective_endpoint(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/agents/objective",
            json={
                "objective": "Reduce monthly cloud cost by 20% without affecting critical applications.",
                "scenario_name": "SaaS",
                "auto_approve": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] is not None
        assert data["approval_required"] is True
        assert data["turn_2_status"] == "done"
        assert "Successfully Applied" in data["final_output"]
