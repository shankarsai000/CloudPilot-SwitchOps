"""
CloudPilot SwitchOps — Integration Tests: REST API for Proposals, Approvals, & Execution (Phase 4)

Validates:
1. POST /api/v1/proposals: proposal creation from DecisionRun.
2. GET /api/v1/proposals/{id} and GET /api/v1/proposals.
3. POST /api/v1/approvals/{id}/token: role enforcement (403 for OPERATOR, 200 for PLATFORM_LEAD).
4. POST /api/v1/approvals/{id}/approve: human approval submission.
5. GET /api/v1/approvals/{id}: status query.
6. POST /api/v1/executions/{id}/execute: isolated workspace bounded execution.
7. GET /api/v1/executions/{id}: execution record query.
8. GET /api/v1/executions/{id}/audit: cryptographic audit trail retrieval.
9. POST /api/v1/approvals/{id}/reject: human rejection lifecycle.
"""

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.domain.approvals import ApproverRole
from app.domain.models import Task, TaskStatus
from app.domain.objectives import PreferenceProfile
from app.main import create_app
from app.persistence.repository import SQLiteTaskRepository
from app.services.decision.decision_orchestrator import DecisionOrchestrator
from app.services.discovery.engine import InfrastructureDiscoveryEngine
from app.services.specialists.finops_specialist import FinOpsSpecialist
from app.services.specialists.secops_specialist import SecOpsSpecialist


@pytest.fixture
def api_client(tmp_path: Path):
    db_file = tmp_path / "api_test.db"
    repo = SQLiteTaskRepository(db_path=str(db_file))

    # Pre-populate a task, assessment, and decision run for samples/staging
    task = Task(
        task_id="task-api-001",
        task_type="decision_optimization",
        title="API Test Task",
        description="Assessment and decision run for API tests",
        room_id="cloudpilot-ops",
        requested_by="@test-user:switch",
        status=TaskStatus.COMPLETED,
    )
    repo.save_task(task)

    discovery_eng = InfrastructureDiscoveryEngine()
    inventory = discovery_eng.discover_workspace("samples/staging")
    inventory.task_id = task.task_id
    repo.save_inventory(inventory)

    finops_res = FinOpsSpecialist().analyze(inventory, task_id=task.task_id)
    for f in finops_res.findings:
        repo.save_finding(f)
    secops_res = SecOpsSpecialist().analyze(inventory, task_id=task.task_id)
    for f in secops_res.all_findings:
        repo.save_finding(f)

    from app.domain.finding import AssessmentSummary
    assessment = AssessmentSummary(
        task_id=task.task_id,
        workspace_root="samples/staging",
        total_resources=inventory.total_resources,
        estimated_monthly_cost=str(finops_res.total_monthly_cost),
        currency="USD",
        total_findings=len(secops_res.security_findings) + len(secops_res.reliability_findings),
        critical_findings_count=0,
        high_findings_count=1,
        medium_findings_count=0,
        low_findings_count=0,
        finops_summary=finops_res.summary_text,
        secops_summary=secops_res.security_summary,
        reliability_summary=secops_res.reliability_summary,
        status="COMPLETED",
    )
    repo.save_assessment(assessment)

    orchestrator = DecisionOrchestrator(repository=repo)
    decision_run, report = orchestrator.run_decision_analysis(
        task_id=task.task_id,
        preference_profile=PreferenceProfile.BALANCED,
    )

    app = create_app()

    # Wire repository dependency overrides
    from app.api.approvals import get_repository as approvals_get_repo
    from app.api.executions import get_repository as executions_get_repo
    app.dependency_overrides[approvals_get_repo] = lambda: repo
    app.dependency_overrides[executions_get_repo] = lambda: repo

    client = TestClient(app)
    return client, decision_run.decision_id, repo


class TestExecutionAPI:

    def test_proposals_approvals_and_execution_lifecycle_api(self, api_client):
        client, decision_id, repo = api_client

        auth_headers_lead = {
            "x-user-id": "lead-platform",
            "x-user-role": ApproverRole.PLATFORM_LEAD.value,
        }
        unauth_headers_operator = {
            "x-user-id": "junior-ops",
            "x-user-role": ApproverRole.OPERATOR.value,
        }

        # 1. Generate Proposal from Decision
        create_resp = client.post(
            "/api/v1/proposals",
            json={
                "decision_id": decision_id,
                "workspace_root": "samples/staging",
                "ttl_seconds": 7200,
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        proposal_data = create_resp.json()
        proposal_id = proposal_data["proposal_id"]
        assert proposal_id.startswith("prop-")
        assert proposal_data["status"] == "PENDING_APPROVAL"
        assert len(proposal_data["before_state_file_hashes"]) > 0

        # 2. Get Proposal by ID
        get_prop_resp = client.get(f"/api/v1/proposals/{proposal_id}")
        assert get_prop_resp.status_code == 200
        assert get_prop_resp.json()["proposal_id"] == proposal_id

        # 3. List Proposals
        list_resp = client.get("/api/v1/proposals")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        # 4. Request Token with Unauthorized Role (OPERATOR) -> 403 Forbidden
        unauth_token_resp = client.post(
            f"/api/v1/approvals/{proposal_id}/token",
            json={"ttl_seconds": 3600},
            headers=unauth_headers_operator,
        )
        assert unauth_token_resp.status_code == 403

        # 5. Request Token with Authorized Role (PLATFORM_LEAD) -> 200 OK
        token_resp = client.post(
            f"/api/v1/approvals/{proposal_id}/token",
            json={"ttl_seconds": 3600},
            headers=auth_headers_lead,
        )
        assert token_resp.status_code == 200, token_resp.text
        token_data = token_resp.json()
        assert "token" in token_data
        token_str = token_data["token"]
        assert token_str.startswith("v1.")

        # 6. Submit Approval -> 200 OK
        approve_resp = client.post(
            f"/api/v1/approvals/{proposal_id}/approve",
            json={"token": token_str},
            headers=auth_headers_lead,
        )
        assert approve_resp.status_code == 200, approve_resp.text
        approval_rec = approve_resp.json()
        assert approval_rec["status"] == "APPROVED"
        assert approval_rec["approver_id"] == "lead-platform"

        # 7. Get Approval Record -> 200 OK
        get_appr_resp = client.get(f"/api/v1/approvals/{proposal_id}")
        assert get_appr_resp.status_code == 200
        assert get_appr_resp.json()["status"] == "APPROVED"

        # 8. Execute Proposal via API -> 200 OK
        exec_resp = client.post(
            f"/api/v1/executions/{proposal_id}/execute",
            json={"token": token_str, "target_workspace_root": "samples/staging"},
            headers=auth_headers_lead,
        )
        assert exec_resp.status_code == 200, exec_resp.text
        exec_data = exec_resp.json()
        assert exec_data["status"] == "COMPLETED"
        execution_id = exec_data["execution_id"]
        assert "live cloud mutation" in exec_data["disclaimer"].lower()

        # 9. Get Execution Status -> 200 OK
        get_exec_resp = client.get(f"/api/v1/executions/{execution_id}")
        assert get_exec_resp.status_code == 200
        assert get_exec_resp.json()["status"] == "COMPLETED"

        # 10. Get Cryptographic Audit Trail -> 200 OK
        audit_resp = client.get(f"/api/v1/executions/{execution_id}/audit")
        assert audit_resp.status_code == 200
        audit_trail = audit_resp.json()
        assert len(audit_trail) >= 4
        # Verify hash chaining in audit trail
        for i in range(1, len(audit_trail)):
            assert audit_trail[i]["prev_audit_hash"] == audit_trail[i - 1]["audit_hash"]

    def test_rejection_api(self, api_client):
        client, decision_id, _ = api_client

        auth_headers_lead = {
            "x-user-id": "lead-platform",
            "x-user-role": ApproverRole.PLATFORM_LEAD.value,
        }

        # Create proposal
        create_resp = client.post(
            "/api/v1/proposals",
            json={"decision_id": decision_id, "workspace_root": "samples/staging"},
        )
        prop_id = create_resp.json()["proposal_id"]

        # Reject proposal
        reject_resp = client.post(
            f"/api/v1/approvals/{prop_id}/reject",
            json={"reason": "Audit freeze in effect"},
            headers=auth_headers_lead,
        )
        assert reject_resp.status_code == 200, reject_resp.text
        rec = reject_resp.json()
        assert rec["status"] == "REJECTED"
        assert rec["rejection_reason"] == "Audit freeze in effect"

        # Check proposal status is REJECTED
        get_prop = client.get(f"/api/v1/proposals/{prop_id}")
        assert get_prop.json()["status"] == "REJECTED"
