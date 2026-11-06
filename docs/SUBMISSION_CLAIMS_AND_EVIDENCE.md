# CloudPilot SwitchOps — Submission Claims & Evidence Matrix

**Project:** CloudPilot SwitchOps  
**Track:** Flip the Switch — Track 01: Best Business Workflow  
**Release Tag:** `v4.3.0-submission-ready`  

---

## Complete Claim-to-Evidence Verification Matrix

This matrix maps every architectural, functional, security, and algorithmic claim made in the CloudPilot SwitchOps submission to its exact source code location, automated test file, and standalone execution evidence.

| Claim ID | Product & Architectural Claim | Source Code Implementation | Automated Test Evidence | Standalone Demonstration Script |
| :--- | :--- | :--- | :--- | :--- |
| **CLM-01** | **Deterministic AST Infrastructure Discovery** | `app/services/discovery/hcl_parser.py`<br>`app/services/discovery/compose_parser.py` | `tests/unit/test_discovery.py`<br>`tests/integration/test_assessment_flow.py` | `scripts/demo_submission.py`<br>(Steps 03–05) |
| **CLM-02** | **Cross-Provider Normalization & Dependency Graph** | `app/domain/models.py`<br>`app/services/discovery/normalizer.py` | `tests/unit/test_normalization.py` | `scripts/demo_submission.py`<br>(Step 04) |
| **CLM-03** | **FinOps Catalog Pricing with Offline Disclosure** | `app/services/specialists/finops.py`<br>`app/services/specialists/pricing_catalog.py` | `tests/unit/test_finops.py` | `scripts/demo_submission.py`<br>(Step 06) |
| **CLM-04** | **SecOps Deterministic Rule Evaluation** | `app/services/specialists/secops.py`<br>`app/services/specialists/security_rules.py` | `tests/unit/test_secops.py` | `scripts/demo_submission.py`<br>(Step 07) |
| **CLM-05** | **SRE Reliability & SPOF Analysis** | `app/services/specialists/sre.py` | `tests/unit/test_sre.py` | `scripts/demo_submission.py`<br>(Step 08) |
| **CLM-06** | **4-Objective Pareto Frontier Optimization** | `app/services/decision/pareto_optimizer.py`<br>`app/domain/objectives.py` | `tests/unit/test_pareto.py` | `scripts/demo_submission.py`<br>(Steps 10, 12) |
| **CLM-07** | **Formal Z3 SMT Constraint Proving (SAT/UNSAT)** | `app/services/decision/constraint_engine.py`<br>`app/domain/decisions.py` | `tests/unit/test_z3_constraints.py` | `scripts/demo_submission.py`<br>(Step 11) |
| **CLM-08** | **Aggregate Composite Budget Ceiling Invariant** | `app/services/decision/constraint_engine.py` | `tests/unit/test_z3_constraints.py` | `scripts/demo_submission.py`<br>(Step 11) |
| **CLM-09** | **Cryptographic SHA-256 Proposal Locking** | `app/services/approval/approval_service.py`<br>`app/domain/proposals.py` | `tests/unit/test_approval_service.py` | `scripts/demo_submission.py`<br>(Step 13) |
| **CLM-10** | **14-Point Governance Review Checklist** | `app/services/approval/approval_service.py`<br>`docker/static/index.html` | `tests/unit/test_approval_service.py` | `scripts/demo_submission.py`<br>(Step 15) |
| **CLM-11** | **Server-Side RBAC & Identity Enforcement** | `app/services/approval/auth_provider.py`<br>`app/domain/approvals.py` | `tests/unit/test_approval_auth.py` | `scripts/demo_submission_negative.py`<br>(Gate 2) |
| **CLM-12** | **Cryptographically Signed HMAC Approval Tokens** | `app/services/approval/approval_service.py`<br>`app/services/approval/token_manager.py` | `tests/unit/test_approval_service.py` | `scripts/demo_submission.py`<br>(Step 16) |
| **CLM-13** | **Bounded Local Workspace Sandboxing** | `app/services/execution/workspace_manager.py`<br>`app/services/execution/execution_orchestrator.py` | `tests/unit/test_execution_orchestrator.py` | `scripts/demo_submission.py`<br>(Step 17) |
| **CLM-14** | **Zero Live Cloud Mutations (Hard Boundary)** | `app/services/execution/execution_policy.py` | `tests/unit/test_execution_orchestrator.py` | `scripts/demo_submission_negative.py`<br>(Gate 5) |
| **CLM-15** | **Independent Syntactic AST Re-Parsing** | `app/services/execution/verification_engine.py` | `tests/unit/test_verification_rollback.py` | `scripts/demo_submission.py`<br>(Step 17) |
| **CLM-16** | **Atomic Rollback Snapshot Recovery** | `app/services/execution/rollback_manager.py` | `tests/unit/test_verification_rollback.py` | `scripts/demo_submission_negative.py`<br>(Gate 5) |
| **CLM-17** | **Switch Dual-Mode Protocol (WS + REST)** | `app/integrations/switch/client.py`<br>`app/integrations/switch/connection_manager.py` | `tests/unit/test_switch_adapter.py`<br>`tests/integration/test_switch_live_workflow.py` | `scripts/demo_submission.py`<br>(Steps 02, 14, 18) |
| **CLM-18** | **Truthful Integration Telemetry & Fallback** | `app/integrations/switch/health.py`<br>`app/integrations/switch/mock_bridge.py` | `tests/unit/test_switch_adapter.py` | `evidence/phase4.3/switch-live-verification.md` |
| **CLM-19** | **Tamper Detection via Pre-Mutation Hash Drift** | `app/services/execution/execution_policy.py` | `tests/unit/test_execution_orchestrator.py` | `scripts/demo_submission_negative.py`<br>(Gate 3) |
| **CLM-20** | **Replay Attack Prevention for Consumed Tokens** | `app/services/approval/approval_service.py` | `tests/unit/test_approval_service.py` | `scripts/demo_submission_negative.py`<br>(Gate 4) |
| **CLM-21** | **Unified Operator Control Room at /dashboard** | `app/main.py`<br>`docker/static/index.html`<br>`docker/static/app.js` | `tests/integration/test_dashboard_mount.py` | Live UI at `http://localhost:8000/dashboard` |
| **CLM-22** | **Correlated End-to-End Audit Trail** | `app/persistence/repository.py` | `tests/integration/test_audit_trail.py` | `scripts/demo_submission.py`<br>(Step 18 & Summary) |

---

## Verification Reproducibility Statement

All claims can be verified independently on any standard workstation running Python 3.11+ without cloud provider credentials or proprietary third-party software. Run:

```bash
pytest tests docker/tests/test_platform_foundation.py -v
python scripts/demo_submission.py
python scripts/demo_submission_negative.py
```
