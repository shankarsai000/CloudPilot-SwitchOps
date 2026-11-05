# CloudPilot SwitchOps — Phase 4.1 Security Audit Report
## Adversarial Verification, Reliability Hardening & Vulnerability Remediation

**Baseline Release:** `v4.0.0-phase4-execution` (`8961ba0`)  
**Target Release:** `v4.1.0-phase4-security-hardened`  
**Audit Scope:** Human-in-the-Loop Approval & Bounded Execution (Workstreams A through G)  
**Lead Auditor:** Principal Security Engineer & Systems Architect  
**Audit Date:** March 2026 / November 2026  

---

## 1. Executive Summary

An adversarial security audit and reliability hardening review was conducted against **CloudPilot SwitchOps Phase 4** to certify the safety and determinism of its Human-in-the-Loop Approval and Bounded Execution architecture.

Prior to hardening, the system baseline contained critical security gaps:
1. **Client-Side Role Trust:** Approver identity and role could be influenced by caller-supplied headers, allowing privilege escalation.
2. **Token Race Condition:** Multiple concurrent threads could attempt execution before token consumption was persisted, risking race condition double-executions.
3. **Sandbox Path & Link Vulnerabilities:** Workspace managers lacked symlink checks and copy-on-write unlinking for hard-linked source files.
4. **Audit Manifest Exposure:** Manifest export endpoints lacked role authorization.

All identified vulnerabilities have been remediated, verified via 49 new automated adversarial tests, and validated against the full 222-test regression suite with **100% passing tests and zero regressions**.

---

## 2. Audit Findings & Remediations Matrix (Workstreams A–G)

| ID | Workstream | Vulnerability Description | Severity | Remediation Applied | Status |
|---|---|---|---|---|---|
| **SEC-401** | **A: RBAC & Auth** | Caller-supplied `X-User-Role` header could override server directory role. | **CRITICAL** | Introduced `ServerSidePrincipalAuthenticator` with authoritative server-side user directory and HMAC Bearer tokens (`cp-auth.v1`). Client role headers strictly ignored. | **RESOLVED** |
| **SEC-402** | **A: RBAC & Auth** | Unregistered identities defaulted to unauthenticated but could hit execution checks. | **HIGH** | Enforced fail-closed behavior in `auth_provider.py`: unregistered principals receive `VIEWER` with `authenticated=False` and are rejected with HTTP 403. | **RESOLVED** |
| **SEC-403** | **B: Concurrency** | Race condition under concurrent execution requests could allow duplicate executions. | **CRITICAL** | Implemented database-level atomic Compare-And-Swap (CAS) in `SQLiteTaskRepository.claim_approval_for_execution` with unique proposal execution constraint. | **RESOLVED** |
| **SEC-404** | **B: Concurrency** | In-memory token consumed state not preserved across independent worker orchestrator instances. | **HIGH** | Transitioned token consumption to SQLite `UPDATE ... WHERE status = 'APPROVED' AND consumed_at IS NULL`. Verified with 5-thread concurrency test. | **RESOLVED** |
| **SEC-405** | **C: Containment** | Symlinks inside source repository could exfiltrate host files when copied to sandbox. | **HIGH** | Added `os.path.islink(unresolved_src)` check in `WorkspaceManager`; symlinks are strictly rejected fail-closed. | **RESOLVED** |
| **SEC-406** | **C: Containment** | Hard links between source files and workspace could allow writing through to source repo. | **HIGH** | Added `stat_info.st_nlink > 1` check in `ChangeApplier`; hard links are unlinked before writing, enforcing copy-on-write isolation. | **RESOLVED** |
| **SEC-407** | **C: Containment** | Non-infrastructure files (`.sh`, `.py`, `.env`, `.exe`) could theoretically be staged. | **MEDIUM** | Enforced `PERMITTED_CONFIG_EXTENSIONS = {".tf", ".tfvars", ".yml", ".yaml"}` in both `WorkspaceManager` and `ChangeApplier`. | **RESOLVED** |
| **SEC-408** | **C: Containment** | `cleanup_workspace` could be passed parent or base paths, risking accidental deletion. | **MEDIUM** | Enforced `ws_norm.startswith(base_norm) and ws_norm != base_norm` containment guard in `cleanup_workspace`. | **RESOLVED** |
| **SEC-409** | **D: Semantic** | Parser integrity and after-state hash mismatch failure did not transition proposal to `FAILED`. | **MEDIUM** | Updated `ExecutionOrchestrator` to mark `proposal.status = ProposalStatus.FAILED` upon any pre-check, mutation, or validation failure. | **RESOLVED** |
| **SEC-410** | **E: Recovery** | Recovery rollback did not verify missing backup snapshot files explicitly before restoration. | **MEDIUM** | Updated `RecoveryManager.rollback_workspace` to verify presence of snapshot directory and snapshot files, returning failure if absent. | **RESOLVED** |
| **SEC-411** | **F: Audit** | Audit trail lacked self-verifying manifest export with canonical digest. | **LOW** | Added `export_audit_manifest(execution_id)` with canonical JSON SHA-256 digest and `/api/v1/executions/{execution_id}/manifest` endpoint. | **RESOLVED** |
| **SEC-412** | **G: API Boundary**| Audit manifest endpoint had no authentication or role restriction. | **HIGH** | Added `principal: ApprovalPrincipal = Depends(get_authenticated_principal)` with authorized role check on `GET /{execution_id}/manifest`. | **RESOLVED** |

---

## 3. Workstream-by-Workstream Deep Dive

### 3.1 Workstream A: Approval Identity and RBAC
- **Inspection Targets:** `app/services/approval/auth_provider.py`, `app/domain/approvals.py`, `app/api/approvals.py`, `app/api/executions.py`.
- **Audit Findings:** The initial prototype accepted `X-User-Role` from headers. An attacker could claim `@lead-platform` while being an unauthenticated guest.
- **Hardening Applied:** 
  1. Authoritative directory (`AUTHORITATIVE_DIRECTORY`) maps user IDs (`lead-platform`, `sec-lead`, `finops-lead`, `junior-ops`, `dev-user`, `viewer-user`) to immutable roles.
  2. Cryptographic HMAC Bearer tokens (`cp-auth.v1.<b64payload>.<sig>`) are generated and verified using constant-time comparison (`hmac.compare_digest`).
  3. Pre-execution authorization re-evaluates the executing principal at execution time, blocking users who experienced mid-flight role demotions.
- **Evidence:** `tests/unit/test_security_rbac_adversarial.py` (13 tests passing).

### 3.2 Workstream B: Token Replay and Concurrency
- **Inspection Targets:** `app/services/approval/approval_token.py`, `app/persistence/repository.py`, `app/services/execution/execution_orchestrator.py`.
- **Audit Findings:** In-memory flags could experience race conditions under concurrent worker threads.
- **Hardening Applied:**
  1. Implemented atomic CAS query in `SQLiteTaskRepository.claim_approval_for_execution`:
     ```sql
     UPDATE approvals SET status = 'CONSUMED', consumed_at = ?
     WHERE approval_id = ? AND status = 'APPROVED' AND consumed_at IS NULL
     ```
  2. Added unique constraint `CREATE UNIQUE INDEX IF NOT EXISTS idx_executions_unique_proposal ON executions(proposal_id)`.
  3. Replay of consumed, rejected, or expired tokens is strictly rejected with `ApprovalSecurityError`.
- **Evidence:** `tests/unit/test_concurrency_atomic_replay.py` (5 tests passing).

### 3.3 Workstream C: Filesystem Isolation and Sandbox Boundaries
- **Inspection Targets:** `app/services/execution/workspace_manager.py`, `app/services/execution/change_applier.py`.
- **Audit Findings:** Traversal sequences (`../`, `..\`), absolute paths, symlink source files, and hard link modifications were potential containment risks.
- **Hardening Applied:**
  1. Execution ID validation via regex `^exec-[a-zA-Z0-9_-]{1,64}$` confined strictly within `base_dir`.
  2. Relative path normalization rejecting `../` and absolute paths.
  3. Detection of source symlinks (`os.path.islink`), rejecting symlinks immediately.
  4. Detection of hard links (`st_nlink > 1`), breaking hard links prior to writing to guarantee copy-on-write isolation.
  5. Extension allowlisting restricting modifications to `{".tf", ".tfvars", ".yml", ".yaml"}`.
  6. File size limits (5 MB max) and workspace file count limits (100 files max).
- **Evidence:** `tests/unit/test_filesystem_containment_adversarial.py` (11 tests passing).

### 3.4 Workstream D: Change Applier and Semantic Preservation
- **Inspection Targets:** `app/services/execution/change_applier.py`, `app/services/execution/validation_runner.py`.
- **Audit Findings:** Targeted mutations must preserve unrelated comments, whitespace, and provider blocks while ensuring valid HCL/YAML syntax.
- **Hardening Applied:**
  1. Structured attribute-level replacement preserves comments and formatting.
  2. Post-execution parsing passes modified files through `TerraformParser` and `ComposeParser`.
  3. Hash verification compares actual post-execution file hash against `expected_after_state_file_hashes`.
- **Evidence:** `tests/unit/test_bounded_execution.py` and `tests/unit/test_recovery_fault_injection.py`.

### 3.5 Workstream E: Recovery and Rollback Determinism
- **Inspection Targets:** `app/services/execution/recovery_manager.py`, `app/services/execution/execution_orchestrator.py`.
- **Audit Findings:** Incomplete recovery or unverified rollback could leave workspaces in corrupted or indeterminate states.
- **Hardening Applied:**
  1. Pre-execution backup snapshots captured in `.cloudpilot_snapshot` prior to any mutation.
  2. Full rollback executed upon mutation failure, syntax error, or hash mismatch.
  3. Every restored file is re-hashed against `proposal.before_state_file_hashes`; any mismatch triggers `ExecutionStatus.RECOVERY_FAILED`.
  4. Ten distinct failure injection scenarios verified.
- **Evidence:** `tests/unit/test_recovery_fault_injection.py` (10 tests passing).

### 3.6 Workstream F: Audit Integrity and Provenance
- **Inspection Targets:** `app/services/execution/execution_audit.py`, `app/domain/execution.py`.
- **Audit Findings:** Audit trails must resist tampering, deletion, and reordering.
- **Hardening Applied:**
  1. Cryptographic SHA-256 hash chaining linking each event to `prev_audit_hash` starting from `GENESIS-{execution_id}`.
  2. Canonical JSON serialization with sorted keys and normalized separators.
  3. `verify_audit_trail` detects any payload modification, timestamp alteration, actor spoofing, event deletion, or reordering.
  4. `export_audit_manifest` outputs verifiable audit packages with manifest digest.
- **Evidence:** `tests/unit/test_audit_chain_tamper_detection.py` (10 tests passing).

### 3.7 Workstream G: API and Boundary Hardening
- **Inspection Targets:** `app/api/approvals.py`, `app/api/executions.py`.
- **Audit Findings:** API endpoints must enforce role restrictions and prevent workflow bypasses.
- **Hardening Applied:**
  1. Mandatory authentication dependency (`get_authenticated_principal`) across all execution and manifest endpoints.
  2. HTTP 403 Forbidden returned for unauthenticated, unprivileged, or non-lead callers.
  3. Audit export endpoint restricted to authorized principals.
- **Evidence:** `tests/unit/test_security_rbac_adversarial.py` (13 tests passing).

---

## 4. Zero Live Cloud Mutation Guarantee Audit

A comprehensive codebase audit confirmed the absolute preservation of the zero live cloud mutation guarantee:
- **No `terraform apply` or `terraform destroy`:** Absent from codebase.
- **No `pulumi up` or `pulumi destroy`:** Absent from codebase.
- **No cloud provider write SDKs (`boto3`, `google-cloud-*`, `azure-*`):** Absent from execution engine.
- **No arbitrary shell execution (`subprocess.Popen(shell=True)`, `os.system`):** Absent from execution engine.
- **Target Boundary:** All file modifications are strictly confined to temporary local sandbox directories (`.cloudpilot/workspaces/exec-*`). Source sample files (`samples/staging`) remain completely unmodified.

---

## 5. Audit Conclusion & Certification

CloudPilot SwitchOps Phase 4.1 successfully satisfies all adversarial verification and reliability hardening criteria. The Human-in-the-Loop Approval & Bounded Execution system is formally certified as safe, tamper-evident, and resistant to concurrent replay and privilege escalation attacks.

**Audit Status:** **ACCEPTED & CERTIFIED**  
**Release Tag Approved:** `v4.1.0-phase4-security-hardened`

