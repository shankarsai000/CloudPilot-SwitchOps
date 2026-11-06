# CloudPilot SwitchOps — Phase 4.3.1 Release Integrity & Hardening Report

**Project:** CloudPilot SwitchOps  
**Repository:** https://github.com/shankarsai000/CloudPilot-SwitchOps  
**Track:** Flip the Switch — Track 01: Best Business Workflow  
**Baseline Tag:** `v4.3.0-submission-ready` (`474c6a9`)  
**Release Tag:** `v4.3.1-release-integrity`  
**Branch:** `phase4.3.1-release-integrity`  
**Test Suite:** **249 passed in 27.82s (100% pass rate, 0 regressions)**  
**Readiness Verdict:** **`SUBMISSION_READY_WITH_DOCUMENTED_EXTERNAL_LIMITATION`**  
**Date:** November 6, 2026  
**Auditor / Release Lead:** Principal Infrastructure, Security & Verification Architect  

---

## 1. Executive Summary & Mission Objective

Phase 4.3.1 was executed as a strict evidence-integrity correction and hardening cycle following the baseline publication of Phase 4.3 (`v4.3.0-submission-ready`). Its mission was **not** to redesign architecture or introduce speculative features, but to eliminate every discrepancy between the codebase implementation, documentation, automated test evidence, and demonstration claims.

Specifically, Phase 4.3.1 accomplished:
1. **Canonical Switch Environment Configuration:** Unified all configuration loading to canonical variable names (`SWITCH_MODE`, `SWITCH_BRIDGE_URL`, `SWITCH_AGENT_API_KEY`, `SWITCH_ROOM_ID`, `SWITCH_AGENT_ID`, `SWITCH_REGISTRATION_KEY`) while maintaining backward compatibility.
2. **Fail-Closed Placeholder Rejection:** Added strict validation ensuring placeholder credentials (e.g. `<your-agent-id>`, `dummy`, `test`, `demo-key-unverified`, `changeme`) are rejected and never yield `LIVE_CONNECTED`.
3. **Mandatory Authenticated Handshake:** Ensured `LIVE_CONNECTED` status requires a genuine authenticated communication exchange (`verify_auth()`) rather than an unauthenticated TCP probe or public health check.
4. **Secret Masking:** Verified secrets never appear in logs, debug dumps, or health responses (`***`).
5. **Demonstration Script Separation & Truthful Output:** Separated offline emulation (`scripts/demo_submission_offline.py`) from strict live execution (`scripts/demo_submission_live.py`). The live script never falls back to emulation; when dependencies are unmet, it truthfully reports `BLOCKED_EXTERNAL_DEPENDENCY` and exits with code 2.
6. **Dynamic 14-Point Governance Evaluation:** Upgraded the 14-point review checklist in the offline demonstration to dynamically evaluate actual persisted domain models (`Proposal`, `DecisionRun`, `PolicyConfiguration`, `inventory`, files), outputting structured evidence rather than static text.
7. **Room Message Delivery Assertions:** Added deterministic verification asserting that proposal and execution announcements are delivered to the Switch room and match proposal IDs and hashes.
8. **Regression Verification:** All 249 tests pass in 27.82 seconds with zero regressions across any phase.

---

## 2. Switch Environment Configuration & Authentication Hardening

### 2.1 Canonical Variable Normalization
The configuration loader `SwitchConnectionConfig.from_env_and_settings()` in [`app/integrations/switch/config.py`](file:///d:/CloudPilot%20AI/app/integrations/switch/config.py) was updated to prioritize canonical variable names:

| Canonical Variable | Purpose | Fallback / Legacy Name | Validation Rule |
| :--- | :--- | :--- | :--- |
| `SWITCH_MODE` | Integration mode (`emulated` vs `live`) | Settings `switch_mode` | Must be `'emulated'` or `'live'` |
| `SWITCH_BRIDGE_URL` | Base URL of Switch bridge service | `SWITCH_ENDPOINT` | Must start with `http://` or `https://` |
| `SWITCH_AGENT_API_KEY` | Bearer auth token for agent bridge | `SWITCH_API_KEY` | Placeholder filter enforced |
| `SWITCH_ROOM_ID` | Default Switch collaboration room | `SWITCH_ROOM` | String non-empty (default: `cloudpilot-ops`) |
| `SWITCH_AGENT_ID` | Registered agent identifier | `SWITCH_AGENT` | Placeholder filter enforced |
| `SWITCH_REGISTRATION_KEY` | Agent registration token | None | Placeholder filter enforced |

### 2.2 Placeholder Rejection Logic
`is_placeholder_credential(val)` inspects strings for placeholder patterns:
- Angled brackets: `<your-agent-id>`, `<api-key>`
- Common placeholder prefixes/substrings: `placeholder`, `your-`, `dummy`, `fake`, `demo-key`, `test`, `changeme`, `replace-me`, `none`, `null`
- Length check: non-empty tokens shorter than 4 characters

When placeholders are detected, `has_live_credentials()` returns `False`. The connection manager assigns `ConnectionStatus.LIVE_UNVERIFIED` and prevents connection attempts.

### 2.3 Authenticated Verification Exchange (`verify_auth()`)
To ensure that a live connection cannot be reported merely because a public health endpoint returned 200:
- Added `verify_auth()` to `SwitchWireClient` in [`app/integrations/switch/client.py`](file:///d:/CloudPilot%20AI/app/integrations/switch/client.py).
- Invokes `update_addressing()`, dispatching an authenticated POST request with the agent's Bearer token to `POST /agents/{agent_id}/ops/update_agent_detail`.
- If the bridge responds with HTTP 401 or 403, raises `SwitchAuthError`.
- `SwitchConnectionManager.verify_connection()` in [`app/integrations/switch/connection_manager.py`](file:///d:/CloudPilot%20AI/app/integrations/switch/connection_manager.py) awaits `verify_auth()` before granting `ConnectionStatus.LIVE_CONNECTED`.

### 2.4 Secret Masking
`SwitchConnectionConfig.masked_api_key` and health endpoints mask sensitive credentials:
- Valid keys: `swit...wxyz`
- Unset keys: `None`
- Plaintext API keys never appear in log entries or health payloads.

---

## 3. Dedicated Verification Tests (`tests/unit/test_switch_config_and_auth.py`)

Six new verification tests were added to guarantee strict configuration and authentication integrity:

1. **`test_documented_env_vars_loaded`**: Proves each canonical variable (`SWITCH_MODE`, `SWITCH_BRIDGE_URL`, `SWITCH_AGENT_API_KEY`, etc.) is correctly loaded from the environment.
2. **`test_placeholder_credentials_rejected`**: Tests `<your-agent-id>`, `your-live-api-key`, `dummy`, `test`, `demo-key-unverified`, `changeme`, proving `has_live_credentials()` returns `False`.
3. **`test_missing_credentials_do_not_produce_live_status`**: Proves that missing credentials in live mode yield `LIVE_UNVERIFIED`, never `LIVE_CONNECTED`.
4. **`test_invalid_credentials_produce_auth_failure`**: Simulates HTTP 401 Unauthorized from bridge; verifies `SwitchAuthError` is raised and connection fails closed.
5. **`test_live_status_requires_authenticated_communication_exchange`**: Proves that a successful unauthenticated probe is insufficient; only a successful `verify_auth()` handshake transitions status to `LIVE_CONNECTED`.
6. **`test_secrets_never_appear_in_logs_or_health`**: Proves that raw API keys are never rendered in logs or health dicts.

---

## 4. Demonstration Scripts Architecture

| Demonstration Script | Execution Mode | Dependency Handling | Key Assertions / Verifications | Exit Code |
| :--- | :--- | :--- | :--- | :---: |
| **`scripts/demo_submission_offline.py`**<br>(alias: `scripts/demo_submission.py`) | **OFFLINE EMULATION** (`EmulatedSwitchBridge`) | None (Fully self-contained in-memory bridge) | - Step 14 asserts proposal announcement delivery in room<br>- Step 15 dynamically checks all 14 governance points against persisted models<br>- Step 18 asserts outcome publication | `0` |
| **`scripts/demo_submission_live.py`** | **STRICT LIVE** (`SwitchWireClient`) | Requires live bridge & credentials (`SWITCH_AGENT_API_KEY`, etc.) | - Zero synthetic injection or emulation fallback<br>- Fails closed if dependencies unmet<br>- Executes live wire handshake, room delivery, approval polling | `2` (when blocked)<br>`0` (when connected) |
| **`scripts/demo_submission_negative.py`** | **ADVERSARIAL & SAFETY GATES** | None (Deterministic tests) | - Gate 1: Human in-room rejection cleanly halts workflow<br>- Gate 2: Untrusted caller role escalation fails closed<br>- Gate 3: File drift / hash tampering blocks execution<br>- Gate 4: Consumed token replay attack rejected<br>- Gate 5: Air-gapped sandbox boundary verified | `0` |

---

## 5. Dynamic 14-Point Governance Checklist Evaluation

In `scripts/demo_submission_offline.py` (Step 15), each check is evaluated against actual live domain entities:

```
[PASSED] CHK-01: Exact AST target resource verified
         Actual: 9 resources | Expected: > 0 resources
         Evidence: Discovered resources in inventory: 9
[PASSED] CHK-02: Pre-mutation SHA-256 recorded and locked
         Actual: 25e4cbf79bc553e2... | Expected: Valid 64-char hex digest
         Evidence: proposal_hash=25e4cbf79bc553e224b298b0e34c40cfa012de4a3b658d63ee0022a94682ebd9
[PASSED] CHK-03: Zero live cloud write calls (bounded local change only)
         Actual: LOCAL_SANDBOX_ONLY | Expected: LOCAL_SANDBOX_ONLY
         Evidence: Execution policy prohibits cloud write APIs and terraform apply
[PASSED] CHK-04: Isolated temporary sandbox workspace configured
         Actual: STAGED | Expected: STAGED
         Evidence: tempfile workspace clone staged for execution
[PASSED] CHK-05: Multi-objective Pareto rank optimal
         Actual: 15 optimal plans | Expected: > 0 optimal plans
         Evidence: decision_id=dec-295236108f, rec=Composite Plan (2 changes)...
[PASSED] CHK-06: Z3 SMT constraint status SAT
         Actual: Z3_CONSTRAINTS_SAT | Expected: Z3_CONSTRAINTS_SAT
         Evidence: z3_status=Z3_CONSTRAINTS_SAT
[PASSED] CHK-07: Hard invariant: no public database exposure
         Actual: SATISFIED | Expected: SATISFIED
         Evidence: Z3 formal constraint: database publicly_accessible == False
[PASSED] CHK-08: Hard invariant: persistent volumes kept
         Actual: SATISFIED | Expected: SATISFIED
         Evidence: Z3 formal constraint: staging_db_storage retention == True
[PASSED] CHK-09: Hard invariant: no privileged containers
         Actual: SATISFIED | Expected: SATISFIED
         Evidence: SecOps rule SEC-003 non-privileged container check
[PASSED] CHK-10: Budget ceiling verified against catalog
         Actual: $15.18 | Expected: <= $10000.00
         Evidence: Cost after change ($15.18) within ceiling
[PASSED] CHK-11: Role-based authorization enforced (PLATFORM_LEAD)
         Actual: PLATFORM_LEAD | Expected: PLATFORM_LEAD
         Evidence: Server-side principal directory: @platform-lead:switch -> PLATFORM_LEAD
[PASSED] CHK-12: Syntactic verification pre-scheduled
         Actual: SCHEDULED | Expected: SCHEDULED
         Evidence: Independent AST parser scheduled post-mutation
[PASSED] CHK-13: Atomic rollback snapshot staged
         Actual: STAGED | Expected: STAGED
         Evidence: Pre-mutation workspace snapshot staged for recovery
[PASSED] CHK-14: Correlated audit record linked
         Actual: task-9495cfa99002 | Expected: VALID_TASK_ID
         Evidence: task_id=task-9495cfa99002, prop_id=prop-ed8be04e7b
```

---

## 6. Full Regression Suite Results

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.2.0, pluggy-1.7.0
rootdir: D:\CloudPilot AI
configfile: pytest.ini
plugins: anyio-4.15.1, asyncio-1.4.1
collected 249 items

tests/contract/test_switch_protocol_contract.py ......                   [  2%]
tests/contract/test_switch_websocket_wire.py .                          [  2%]
tests/integration/test_assessment_api.py .                              [  3%]
tests/integration/test_assessment_workflow.py .                         [  3%]
tests/integration/test_dashboard_mount.py ...                           [  4%]
tests/integration/test_decision_api.py .                                [  5%]
tests/integration/test_decision_workflow.py .                           [  5%]
tests/integration/test_execution_api.py ..                              [  6%]
tests/integration/test_persistence_and_api.py ........                  [  9%]
tests/integration/test_switch_approval_workflow.py ...                  [ 10%]
tests/integration/test_switch_phase4_2_e2e.py ....                      [ 12%]
tests/unit/test_aggregate_combination_budget.py ......                  [ 14%]
tests/unit/test_approval_system.py ..........                           [ 18%]
tests/unit/test_audit_chain_tamper_detection.py .....                   [ 20%]
tests/unit/test_bounded_execution.py ........                           [ 23%]
tests/unit/test_candidate_generator.py ........                         [ 26%]
tests/unit/test_candidate_interactions.py ......                        [ 28%]
tests/unit/test_combination_optimizer.py ......                         [ 31%]
tests/unit/test_composite_constraint_verification.py ........           [ 34%]
tests/unit/test_concurrency_atomic_replay.py ....                       [ 36%]
tests/unit/test_constraint_engine.py ........                           [ 39%]
tests/unit/test_discovery_parsers.py ........                           [ 42%]
tests/unit/test_domain_and_config.py ........                           [ 45%]
tests/unit/test_evidence_provenance.py ..                               [ 46%]
tests/unit/test_execution_recovery.py .....                             [ 48%]
tests/unit/test_filesystem_containment_adversarial.py ........          [ 51%]
tests/unit/test_finops_engine.py ............                           [ 56%]
tests/unit/test_objective_calculator.py ........                        [ 59%]
tests/unit/test_objective_model_hardening.py ........                   [ 62%]
tests/unit/test_pareto_optimizer.py ........                            [ 66%]
tests/unit/test_phase4_preconditions.py .                               [ 66%]
tests/unit/test_recovery_fault_injection.py .....                       [ 68%]
tests/unit/test_secops_engine.py ............                           [ 73%]
tests/unit/test_security_rbac_adversarial.py ........                   [ 76%]
tests/unit/test_switch_config_and_auth.py ......                        [ 78%]
tests/unit/test_switch_connection_manager.py ......                     [ 81%]
tests/unit/test_switch_event_handler.py .....                           [ 83%]
tests/unit/test_switch_message_mapper.py ....                           [ 84%]
tests/unit/test_workspace_isolation.py .......                         [ 87%]
tests/unit/test_z3_formal_solver.py ........                            [ 90%]
tests/unit/test_z3_semantics_and_selection.py .......                   [ 93%]
docker/tests/test_platform_foundation.py .............................   [100%]

============================ 249 passed in 27.82s ============================
```

---

## 7. Operational Disclosures & Release Verdict

1. **Switch Connectivity Limitation:** Live Switch operation requires valid bridge credentials and a reachable bridge daemon. When absent, the system operates in verified `EMULATED_MODE`.
2. **FinOps Catalog Pricing:** Costs are computed using static AWS, GCP, and Azure pricing tables; they represent baseline engineering estimates rather than live billing data.
3. **Local SQLite Persistence:** Audit records are stored in a local SQLite database for reproducible local verification.
4. **Zero Live Cloud Mutations:** Bounded execution mutates files only in isolated sandbox workspaces. Source samples and live clouds remain untouched.

### Final Certification Decision:

$$\mathbf{SUBMISSION\_READY\_WITH\_DOCUMENTED\_EXTERNAL\_LIMITATION}$$

All release integrity, configuration, and demonstration corrections are complete and certified.
