# CloudPilot SwitchOps — Phase 4.1 Threat Model
## Adversarial Security Analysis & Containment Verification

**Baseline Release:** `v4.0.0-phase4-execution` (`8961ba0`)  
**Target Release:** `v4.1.0-phase4-security-hardened`  
**Classification:** Engineering Security Documentation  
**Date:** March 2026 / November 2026  

---

## 1. Executive Summary & Security Perimeter

CloudPilot SwitchOps introduces human-in-the-loop bounded execution of cloud infrastructure configuration files within isolated sandboxes. Because CloudPilot bridges interactive collaboration (via Switch AI team-chat) with infrastructure configuration files, it presents a critical trust boundary:
**No unverified, unauthorized, replayed, or out-of-scope mutation must ever occur on the underlying filesystem or propagate to cloud environments.**

This Threat Model provides a rigorous security breakdown of CloudPilot SwitchOps Phase 4.1, detailing attacker profiles, trust boundaries, attack surfaces, STRIDE categorizations, and concrete mitigations validated by adversarial automated testing.

---

## 2. Attacker Profiles & Threat Actors

| Threat Actor | Capabilities & Access | Motivation / Objective | Attack Vectors Considered |
|---|---|---|---|
| **Malicious Teammate / Rogue Operator** | Valid network access to API or Switch room; low-privilege role (`OPERATOR`, `DEVELOPER`, `VIEWER`). | Privilege escalation; approving changes without lead authorization; tampering with execution targets. | Caller-supplied header injection (`X-User-Role: PLATFORM_LEAD`), intercepting approval requests, forging approvals. |
| **Compromised Switch Account** | Access to Switch room credentials or session tokens; capability to post room messages. | Triggering arbitrary infrastructure mutations; bypassing approval review. | Posting spoofed execution approval messages; altering proposal hashes in transit. |
| **Network Interceptor (Man-in-the-Middle)** | Network eavesdropping between Switch/API client and CloudPilot backend. | Replay attacks; payload tampering; token stealing. | Replaying consumed HMAC tokens; altering JSON payloads in transit. |
| **Untrusted Repository Author** | Capability to submit pull requests or configuration files containing malicious paths or symlinks. | Arbitrary file read/write on host OS; escaping execution sandbox; exfiltrating secrets (`/etc/passwd`, `.env`, AWS credentials). | Path traversal (`../../etc/passwd`), symbolic links pointing outside workspace, hidden malicious scripts (`.sh`, `.py`, `.exe`). |
| **Concurrent Race Attacker** | High-rate automated client sending simultaneous requests with identical approval tokens. | Double-execution, race condition exploitation, inconsistent state generation. | Firing 10+ concurrent execution requests simultaneously to claim duplicate workspace executions. |
| **Insider Host / Process Attacker** | Ability to interrupt processes, simulate disk-full conditions, or tamper with SQLite storage. | Corrupting files, breaking audit provenance, or asserting success without post-condition verification. | SIGKILL/interruption during write, corrupting database rows, deleting audit log entries. |

---

## 3. Trust Boundaries

```
[ Switch Client / User ]
         |
    (Boundary 1: Network & Identity Authentication)
         v
[ CloudPilot API Gateway / Server-Side Authenticator ]
         |
    (Boundary 2: Application Core & Policy Enforcement)
         v
[ Execution Orchestrator & Task Repository (SQLite) ]
         |
    (Boundary 3: Sandboxed Isolated Workspace Filesystem)
         v
[ Isolated Sandbox Directory (.cloudpilot/workspaces/exec-*) ]
         |
    (Boundary 4: Host OS Boundary [Strict Containment])
         |
   [ Host Filesystem / System Binaries ]
         |
    (Boundary 5: Live Cloud Mutation Boundary [AIR-GAPPED / FORBIDDEN])
         v
   [ AWS / GCP / Azure Live APIs (Zero Mutation / No terraform apply) ]
```

### Trust Boundary Definitions:
1. **Boundary 1: Switch Client / API Caller ↔ Server-Side Authenticator:**  
   Clients are untrusted. Any client-provided role headers (`X-User-Role`, etc.) are ignored. Identity is established via an authoritative server-side user directory and cryptographic HMAC-SHA256 Bearer tokens (`ServerSidePrincipalAuthenticator`).
2. **Boundary 2: API ↔ Execution Orchestrator & Database:**  
   State transitions (PENDING → APPROVED → CONSUMED) require atomic Compare-And-Swap (CAS) in SQLite. No in-flight state transfers without database-level transactional locks.
3. **Boundary 3: Execution Orchestrator ↔ Workspace Filesystem:**  
   The source infrastructure directory (`samples/staging`, repo root) is strictly read-only. File mutations are exclusively performed within an isolated temporary sandbox (`.cloudpilot/workspaces/exec-*`).
4. **Boundary 4: Workspace Filesystem ↔ Host Operating System:**  
   Execution cannot escape the workspace directory. Symlinks pointing to host paths, absolute paths, directory traversal (`../`), and prohibited file extensions (`.py`, `.sh`, `.env`, `.exe`) are rejected fail-closed.
5. **Boundary 5: CloudPilot ↔ Live Cloud Providers:**  
   **Hard Architectural Air-Gap:** Live cloud provider write APIs (`boto3`, `google-api`, `azure-mgmt`), `terraform apply`, `pulumi up`, and arbitrary shell invocations are completely absent and forbidden in the codebase.

---

## 4. Attack Surfaces

1. **REST API Endpoints (`/api/v1/approvals/*`, `/api/v1/executions/*`):**  
   Target for unauthenticated execution triggers, token forgery, parameter tampering, and denial-of-service via malformed payloads.
2. **Cryptographic Approval Tokens (`ApprovalTokenManager`):**  
   Target for replay attacks, bit-flipping HMAC forgery, cross-proposal token reuse, and expiration bypass.
3. **Change Applier (`ChangeApplier`):**  
   Target for regex injection, multi-attribute leakage, arbitrary file modification, and hard link write-through.
4. **Workspace Manager (`WorkspaceManager`):**  
   Target for directory traversal, execution ID injection, symlink exfiltration, resource exhaustion via oversized files, and cleanup path manipulation.
5. **Recovery Manager (`RecoveryManager`):**  
   Target for incomplete rollback, corrupted backup snapshots, and false recovery claims.
6. **Execution Audit Logger (`ExecutionAuditLogger`):**  
   Target for audit trail truncation, event deletion, chronological reordering, and payload tampering.

---

## 5. STRIDE Threat Analysis by Component

| STRIDE Category | Threat Description | Affected Component | Mitigations Implemented in Phase 4.1 | Test Verification |
|---|---|---|---|---|
| **Spoofing** | Attacker claims privileged identity (`@lead-platform`) by passing arbitrary HTTP headers. | `app.api.approvals`, `auth_provider.py` | Authoritative server directory mapping; cryptographic HMAC bearer tokens (`cp-auth.v1`); client-supplied roles ignored. | `test_caller_supplied_role_escalation_rejected`, `test_unregistered_identity_fails_closed` |
| **Tampering** | Attacker tampers with proposed changes or approval token payload in transit. | `ApprovalTokenManager`, `ChangeApplier` | Constant-time HMAC-SHA256 verification (`hmac.compare_digest`); exact `proposal_hash` binding; before/after file hash verification. | `test_forged_hmac_token_rejected_constant_time`, `test_tampered_event_payload_detected` |
| **Repudiation** | Operator approves change but later denies authorization; actions performed without attributable record. | `ExecutionAuditLogger`, `SQLiteTaskRepository` | Append-only cryptographically chained audit events (`prev_audit_hash` chaining to `GENESIS`); verifiable manifest export with SHA-256 digest. | `test_audit_chain_genesis_and_continuity`, `test_manifest_export_and_digest_verification` |
| **Information Disclosure** | Symlink in source directory points to `/etc/passwd` or AWS credentials to exfiltrate contents. | `WorkspaceManager` | Strict symlink detection (`os.path.islink`) on source files; rejection of any symlinks; strict configuration extension allowlist (`.tf`, `.tfvars`, `.yml`, `.yaml`). | `test_symlink_file_in_source_rejected`, `test_prohibited_extensions_rejected` |
| **Denial of Service** | Attacker floods 10+ concurrent execution requests to cause race conditions or staging huge 1GB file. | `WorkspaceManager`, `SQLiteTaskRepository` | Database-level atomic CAS token consumption (`UPDATE ... WHERE status = 'APPROVED' AND consumed_at IS NULL`); 5MB max file size; 100 max files per workspace. | `test_simultaneous_execution_race_condition`, `test_max_file_size_enforced` |
| **Elevation of Privilege** | Low-privilege `OPERATOR` triggers change execution, or `PLATFORM_LEAD` demoted after approval executes proposal. | `ExecutionPolicyEngine`, `ExecutionOrchestrator` | Re-verification of executing principal at execution time; rejection if approver role lacks lead status or was demoted. | `test_unauthorized_execution_rejected`, `test_role_demotion_between_approval_and_execution_fails` |

---

## 6. Threat Mitigations & Defense-in-Depth Mappings

### 6.1 Server-Side Authentication & Authorization
- **Implementation:** `app/services/approval/auth_provider.py` (`ServerSidePrincipalAuthenticator`).
- **Control:** Principal roles are resolved strictly from the authoritative server directory (`AUTHORITATIVE_DIRECTORY`). Request-body or client-supplied role headers cannot alter roles.
- **Fail-Closed:** Unregistered identities receive `ApproverRole.VIEWER` with `authenticated=False` and are immediately blocked with HTTP 403.

### 6.2 Atomic Token Single-Use & Replay Protection
- **Implementation:** `app/persistence/repository.py` (`claim_approval_for_execution`) & `SQLiteTaskRepository`.
- **Control:** Database-level Compare-And-Swap query:
  `UPDATE approvals SET status = 'CONSUMED', consumed_at = ? WHERE approval_id = ? AND status = 'APPROVED' AND consumed_at IS NULL`
- **Result:** Exactly 1 winner in multi-threaded races; duplicate submissions fail closed with `ApprovalSecurityError`.

### 6.3 Sandbox Containment & Hard-Link Breaking
- **Implementation:** `app/services/execution/workspace_manager.py` & `app/services/execution/change_applier.py`.
- **Control:** Target execution directories require valid `exec-[a-zA-Z0-9_-]{1,64}` naming; relative path traversal (`../`) and absolute paths are rejected. Hard links are detected (`stat_info.st_nlink > 1`) and unlinked before write to prevent mutating through linked source files.

### 6.4 Zero Live Cloud Infrastructure Mutations
- **Implementation:** Architectural policy verified across entire codebase.
- **Control:** No `terraform apply`, `terraform destroy`, `pulumi up`, or live cloud provider mutating SDKs exist in the repository. Execution strictly limits modifications to local configuration files within the isolated sandbox.

---

## 7. Residual Risk Assessment & Honest Disclosures

1. **Local SQLite File Boundary:** In a multi-tenant environment, local SQLite files must be protected by OS-level file permissions (`chmod 0600`).
2. **Switch Wire Adapter Bridge:** When running in development/testing mode with `EmulatedSwitchBridge`, Switch protocol messages are emulated in-process; production deployments must supply `SWITCH_AGENT_API_KEY` to connect via TLS to the live Switch Agent Bridge.
3. **OS-Level Process Isolation:** Workspace isolation is currently directory-based with strict path validation and copy-on-write semantics. Containerized namespaces (e.g. Linux cgroups/chroot/Docker sandboxes) should be introduced if untrusted users are granted arbitrary shell execution in future phases.

---
**Certified by:** Antigravity Principal Application Security & Systems Architecture Agent  
**Date:** March 2026 / November 2026

