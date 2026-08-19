"""
test_execution_agent.py

Comprehensive unit and integration test suite for the Autonomous Execution Agent (M10).
Tests provider adapters, router, rollback processes, live monitoring, post-run validation,
policy guardlocks, rollouts, emergency controllers, logging, and FastAPI routes.
"""

import uuid
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from models_execution import ExecutionRecord, ExecutionState, RollbackRecord, RolloutStrategy
from aws_executor import AWSExecutor
from azure_executor import AzureExecutor
from gcp_executor import GCPExecutor
from kubernetes_executor import KubernetesExecutor
from terraform_executor import TerraformExecutor
from ansible_executor import AnsibleExecutor
from provider_router import ProviderRouter
from rollback_engine import RollbackEngine
from monitoring_engine import MonitoringEngine
from validation_engine import ValidationEngine
from policy_guard import PolicyGuard
from rollout_manager import RolloutManager
from emergency_controller import EmergencyController
from execution_logger import ExecutionLogger
from execution_orchestrator import ExecutionOrchestrator
from execution_agent import ExecutionAgent
from execution_routes import create_execution_router


# ═══════════════════════════════════════════════════════════════
# Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestProviderAdapters:
    """Tests all provider execution adapters."""

    def test_aws_adapter(self) -> None:
        exec_aws = AWSExecutor()
        plan = {"target_id": "ec2-instance-1", "action": "RESIZE"}

        assert exec_aws.validate(plan) is True
        res = exec_aws.execute(plan)
        assert res["status"] == "SUCCESS"
        assert res["provider"] == "AWS"

        rb_res = exec_aws.rollback(plan)
        assert rb_res["status"] == "SUCCESS"
        assert "ROLLBACK" in rb_res["action"]

        metrics = exec_aws.monitor(plan)
        assert "CPUUtilization" in metrics

    def test_azure_adapter(self) -> None:
        exec_az = AzureExecutor()
        plan = {"target_id": "azure-vm-1", "action": "RESIZE"}

        assert exec_az.validate(plan) is True
        res = exec_az.execute(plan)
        assert res["status"] == "SUCCESS"

        metrics = exec_az.monitor(plan)
        assert "Percentage CPU" in metrics

    def test_gcp_adapter(self) -> None:
        exec_gcp = GCPExecutor()
        plan = {"target_id": "gcp-instance-1", "action": "RESIZE"}

        assert exec_gcp.validate(plan) is True
        res = exec_gcp.execute(plan)
        assert res["status"] == "SUCCESS"

        metrics = exec_gcp.monitor(plan)
        assert "instance/cpu/utilization" in metrics

    def test_k8s_adapter(self) -> None:
        exec_k8s = KubernetesExecutor()
        plan = {"target_id": "k8s-pod-1", "action": "RESIZE"}

        assert exec_k8s.validate(plan) is True
        res = exec_k8s.execute(plan)
        assert res["status"] == "SUCCESS"

        metrics = exec_k8s.monitor(plan)
        assert "pod/cpu/usage_rate" in metrics

    def test_terraform_adapter(self) -> None:
        exec_tf = TerraformExecutor()
        plan = {"target_id": "tf-workspace-1"}

        assert exec_tf.validate(plan) is True
        res = exec_tf.execute(plan)
        assert res["status"] == "SUCCESS"

        metrics = exec_tf.monitor(plan)
        assert metrics["drift_detected"] is False or "drift_detected" in metrics

    def test_ansible_adapter(self) -> None:
        exec_ans = AnsibleExecutor()
        plan = {"target_id": "ans-host-1"}

        assert exec_ans.validate(plan) is True
        res = exec_ans.execute(plan)
        assert res["status"] == "SUCCESS"

        metrics = exec_ans.monitor(plan)
        assert metrics["tasks_ok"] == 12


class TestProviderRouter:
    """Tests Provider Router targeting."""

    def test_route_by_metadata(self) -> None:
        router = ProviderRouter()
        plan = {"target_id": "res-1", "provider": "GCP"}
        exec_inst = router.get_executor(plan)
        assert isinstance(exec_inst, GCPExecutor)

    def test_route_by_heuristics_aws(self) -> None:
        router = ProviderRouter()
        plan = {"target_id": "ec2-instance-prod"}
        exec_inst = router.get_executor(plan)
        assert isinstance(exec_inst, AWSExecutor)

    def test_route_by_heuristics_k8s(self) -> None:
        router = ProviderRouter()
        plan = {"target_id": "k8s-deployment-frontend"}
        exec_inst = router.get_executor(plan)
        assert isinstance(exec_inst, KubernetesExecutor)


class TestRollbackEngine:
    """Tests Rollback Engine processes."""

    def test_rollback_success(self) -> None:
        engine = RollbackEngine()
        plan = {"strategy": "revert-snapshot"}
        res = engine.execute_rollback(
            execution_id="exec-1", target_id="ec2-res", action="RESIZE",
            trigger_reason="CPU Spike", rollback_plan=plan
        )

        assert res.status == "COMPLETED"
        assert res.rollback_id.startswith("rbk-")
        assert "RESTORATION_VERIFIED" in res.details["phase"]


class TestMonitoringEngine:
    """Tests Telemetry monitoring and anomalies detection."""

    def test_metrics_collection(self) -> None:
        engine = MonitoringEngine()
        metrics = engine.collect_metrics("ec2-1", "AWS")

        assert "cpu_percent" in metrics
        assert "memory_percent" in metrics
        assert metrics["availability"] == 1.0

    def test_detect_cpu_anomaly(self) -> None:
        engine = MonitoringEngine(max_cpu_percent=80.0)
        metrics = {"cpu_percent": 95.0, "error_rate": 0.0, "latency_ms": 100.0}

        is_anomaly, reason = engine.detect_anomaly(metrics)
        assert is_anomaly is True
        assert "CPU" in reason

    def test_detect_latency_anomaly(self) -> None:
        engine = MonitoringEngine(max_latency_ms=500.0)
        metrics = {"cpu_percent": 30.0, "error_rate": 0.0, "latency_ms": 700.0}

        is_anomaly, reason = engine.detect_anomaly(metrics)
        assert is_anomaly is True
        assert "Latency" in reason

    def test_detect_error_rate_anomaly(self) -> None:
        engine = MonitoringEngine(max_error_rate=0.02)
        metrics = {"cpu_percent": 30.0, "error_rate": 0.05, "latency_ms": 100.0}

        is_anomaly, reason = engine.detect_anomaly(metrics)
        assert is_anomaly is True
        assert "Error rate" in reason


class TestValidationEngine:
    """Tests Post-execution validation verification."""

    def test_validation_success(self) -> None:
        engine = ValidationEngine()
        metrics = {"error_rate": 0.001, "latency_ms": 50.0, "availability": 1.0}
        success, msgs = engine.validate_post_execution("ec2-1", "RESIZE", "AWS", metrics)

        assert success is True
        assert any("passed" in m.lower() or "success" in m.lower() for m in msgs)


class TestPolicyGuard:
    """Tests pre-execution safety guardrails."""

    def test_guardrails_passed(self) -> None:
        guard = PolicyGuard()
        meta = {"level": "AUTO_EXECUTE"}
        plan = {"strategy": "revert"}
        success, msgs = guard.verify_guardrails("ec2-1", meta, plan)

        assert success is True
        assert "ec2-1" in guard.acquired_locks

    def test_guardrails_no_level(self) -> None:
        guard = PolicyGuard()
        success, msgs = guard.verify_guardrails("ec2-1", {}, {})

        assert success is False
        assert any("level" in m.lower() for m in msgs)


class TestRolloutManager:
    """Tests canary and progressive rollout steps."""

    def test_direct_rollout(self) -> None:
        manager = RolloutManager()
        progress = manager.initialize_rollout(RolloutStrategy.DIRECT)

        assert progress.current_percentage == 100.0
        progress, finished = manager.advance_rollout(progress)
        assert finished is True

    def test_canary_rollout(self) -> None:
        manager = RolloutManager()
        progress = manager.initialize_rollout(RolloutStrategy.CANARY)

        assert progress.current_percentage == 0.0
        # Step 1: 10%
        progress, finished = manager.advance_rollout(progress)
        assert progress.current_percentage == 10.0
        assert finished is False

        # Step 2: 25%
        progress, finished = manager.advance_rollout(progress)
        assert progress.current_percentage == 25.0
        assert finished is False


class TestEmergencyController:
    """Tests manual emergency controller overrides."""

    def test_pause_and_resume(self) -> None:
        ctrl = EmergencyController()
        record = ExecutionRecord(
            execution_id="exec-1", decision_id="dec-1", target_id="res-1",
            action="RESIZE", state=ExecutionState.RUNNING
        )

        record = ctrl.pause(record, "investigate latency")
        assert record.state == ExecutionState.PAUSED

        record = ctrl.resume(record)
        assert record.state == ExecutionState.RUNNING


# ═══════════════════════════════════════════════════════════════
# Integration & Orchestration Tests
# ═══════════════════════════════════════════════════════════════


class TestExecutionAgent:
    """Tests complete orchestrator flow in the agent."""

    def test_successful_run(self) -> None:
        agent = ExecutionAgent()
        meta = {"level": "AUTO_EXECUTE"}
        plan = {"strategy": "revert-snapshot"}

        record = agent.start_execution(
            decision_id="dec-123",
            target_id="ec2-instance-1",
            action="RESIZE",
            approval_metadata=meta,
            rollback_plan=plan,
            rollout_strategy=RolloutStrategy.DIRECT,
        )

        assert record.state == ExecutionState.COMPLETED
        assert record.lock_acquired is False

    def test_anomaly_triggers_rollback(self) -> None:
        # Inject custom monitoring thresholds to force failure
        mon = MonitoringEngine(max_cpu_percent=10.0)  # very low threshold to force trigger
        orch = ExecutionOrchestrator(monitoring_engine=mon)
        agent = ExecutionAgent(orchestrator=orch)

        meta = {"level": "AUTO_EXECUTE"}
        plan = {"strategy": "revert-snapshot"}

        record = agent.start_execution(
            decision_id="dec-123",
            target_id="ec2-instance-1",
            action="RESIZE",
            approval_metadata=meta,
            rollback_plan=plan,
            rollout_strategy=RolloutStrategy.DIRECT,
        )

        # Anomaly triggers ROLLING_BACK and completes as ROLLED_BACK
        assert record.state == ExecutionState.ROLLED_BACK
        assert len(record.rollback_history) == 1
        assert record.rollback_history[0].status == "COMPLETED"

    def test_cancel_flow(self) -> None:
        agent = ExecutionAgent()
        meta = {"level": "AUTO_EXECUTE"}
        plan = {"strategy": "revert"}

        # Start execution record in memory
        record = agent.start_execution(
            decision_id="dec-123",
            target_id="ec2-instance-1",
            action="RESIZE",
            approval_metadata=meta,
            rollback_plan=plan,
            rollout_strategy=RolloutStrategy.DIRECT,
        )

        # Force state to PENDING and cancel it
        record.state = ExecutionState.PENDING
        cancelled_rec = agent.cancel_execution(record.execution_id, "manual abort")
        assert cancelled_rec.state == ExecutionState.CANCELLED


class TestExecutionAPIRoutes:
    """Tests FastAPI router creation and endpoint lists."""

    def test_create_router(self) -> None:
        agent = MagicMock()
        router = create_execution_router(agent=agent)
        assert router is not None

        paths = [r.path for r in router.routes]
        assert "/api/execution/start" in paths
        assert "/api/execution/pause" in paths
        assert "/api/execution/resume" in paths
        assert "/api/execution/cancel" in paths
        assert "/api/execution/rollback" in paths
        assert "/api/execution/status" in paths
        assert "/api/execution/logs" in paths
        assert "/api/execution/metrics" in paths
        assert "/api/execution/history" in paths
