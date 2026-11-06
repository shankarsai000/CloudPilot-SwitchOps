# CloudPilot SwitchOps — Submission Architecture Specification

**Project:** CloudPilot SwitchOps  
**Document:** Complete System Architecture & Formal Models  
**Release Tag:** `v4.3.0-submission-ready`  
**Track:** Flip the Switch — Track 01: Best Business Workflow  

---

## 1. High-Level System Architecture

CloudPilot SwitchOps implements a modular monolith in Python 3.11+ using FastAPI, Pydantic v2, and SQLite. It bridges human operators in Switch collaboration rooms with deterministic cloud intelligence and formal verification engines.

```mermaid
flowchart TD
    subgraph Layer1 ["1. Collaboration & Interaction Layer"]
        Human["Human Platform Architect (@platform-lead:switch)"]
        SwitchRoom["Switch Collaboration Room: cloudpilot-ops-room"]
        WebDashboard["Operator Control Room Web UI (/dashboard)"]
    end

    subgraph Layer2 ["2. Protocol & Communication Layer"]
        SwitchWS["WebSocket Inbound Client (/agents/{id}/connection/ws)"]
        SwitchREST["REST Outbound Publisher (/rooms/{id}/messages)"]
        TruthfulAdapter["Truthful SwitchConnectionManager (Live vs Emulated)"]
    end

    subgraph Layer3 ["3. Discovery & Specialist Intelligence Layer"]
        ParserHCL["Terraform HCL Parser (python_hcl2 AST)"]
        ParserYAML["Docker Compose Parser (YAML AST)"]
        Normalizer["Resource Normalization & Dependency Graph"]
        FinOpsEngine["FinOps Catalog Pricing & Waste Analysis"]
        SecOpsEngine["SecOps Deterministic Security Rule Engine"]
        SREEngine["SRE Reliability Posture & SPOF Detector"]
    end

    subgraph Layer4 ["4. Decision Intelligence & Formal Proving Layer"]
        CandidateGen["Optimization Candidate Generator"]
        ParetoEngine["4-Objective Pareto Frontier Calculator"]
        Z3Solver["Z3 Theorem Prover (SMT Hard Invariant Solver)"]
        DecisionOrchestrator["Decision Report & Recommendation Synthesizer"]
    end

    subgraph Layer5 ["5. Governance & Human Approval Layer"]
        ProposalLocker["Proposal Manager (SHA-256 State Locking)"]
        ReviewChecklist["14-Point Governance Review Evaluator"]
        AuthDirectory["Server-Side Principal Directory & RBAC Engine"]
        TokenSigner["HMAC-SHA256 Single-Use Approval Token Signer"]
    end

    subgraph Layer6 ["6. Bounded Execution & Recovery Layer"]
        SandboxMgr["Isolated Workspace Sandbox Manager (tempfile copy)"]
        ASTMutator["Bounded AST Mutation Engine (HCL/YAML)"]
        SyntaxVerifier["Independent Syntactic AST Re-Parser"]
        RollbackMgr["Atomic Snapshot Rollback Restorer"]
    end

    subgraph Layer7 ["7. Persistence & Audit Layer"]
        SQLiteRepo["SQLite Correlated Audit Repository"]
        AuditRecord["Lineage: Task -> Decision -> Proposal -> Approval -> Execution"]
    end

    Human <--> SwitchRoom
    SwitchRoom <--> SwitchWS
    SwitchRoom <--> SwitchREST
    WebDashboard <--> SwitchREST
    SwitchWS --> TruthfulAdapter
    TruthfulAdapter --> ParserHCL & ParserYAML
    ParserHCL & ParserYAML --> Normalizer
    Normalizer --> FinOpsEngine & SecOpsEngine & SREEngine
    FinOpsEngine & SecOpsEngine & SREEngine --> CandidateGen
    CandidateGen --> ParetoEngine
    ParetoEngine --> Z3Solver
    Z3Solver --> DecisionOrchestrator
    DecisionOrchestrator --> ProposalLocker
    ProposalLocker --> ReviewChecklist
    ReviewChecklist --> SwitchREST
    SwitchWS --> AuthDirectory
    AuthDirectory --> TokenSigner
    TokenSigner --> SandboxMgr
    SandboxMgr --> ASTMutator
    ASTMutator --> SyntaxVerifier
    SyntaxVerifier -->|Pass| SwitchREST
    SyntaxVerifier -->|Fail| RollbackMgr
    SyntaxVerifier --> SQLiteRepo
    SQLiteRepo --> AuditRecord
```

---

## 2. Multi-Objective Optimization & Z3 Solver Formal Model

CloudPilot formulates infrastructure optimization as a constrained multi-objective problem:

$$\max_{\vec{x}} \left( \Delta \text{Cost}(\vec{x}), -\text{Risk}(\vec{x}), \Delta \text{Reliability}(\vec{x}), -\text{Effort}(\vec{x}) \right)$$

Subject to:

1. **Security Invariant 1 (No Public Database Exposure):**
   $$\forall r \in \text{Resources}, \quad \text{IsDatabase}(r) \implies \neg \text{IsPubliclyAccessible}(r)$$
2. **Security Invariant 2 (Persistent Storage Retention):**
   $$\forall v \in \text{Volumes}, \quad \text{IsPersistentData}(v) \implies \neg \text{IsDeleted}(v)$$
3. **Security Invariant 3 (No Root Privilege Escalation):**
   $$\forall c \in \text{Containers}, \quad \text{Privileged}(c) = \text{False}$$
4. **FinOps Invariant 4 (Aggregate Budget Ceiling):**
   $$\sum_{r} \text{Cost}_{\text{after}}(r) \le \text{BudgetCeiling}$$

```mermaid
flowchart TD
    RawFindings["Specialist Findings (FinOps, SecOps, SRE)"] --> GenCandidates["Generate Single & Composite Candidates"]
    GenCandidates --> CheckPreRules["Deterministic Pre-Filter Rules"]
    CheckPreRules --> BuildZ3["Encode Invariants into Z3 SMT AST"]
    BuildZ3 --> Z3Solve{"Z3 Solver Check"}
    Z3Solve -->|UNSAT| Disqualify["Disqualify Candidate (Record Invariant Failure)"]
    Z3Solve -->|UNKNOWN| FailClosed["Treat as Infeasible (Fail-Closed)"]
    Z3Solve -->|SAT| ParetoSort["Compute 4-Objective Pareto Dominance"]
    ParetoSort --> OptimalRank["Rank Pareto Frontier (Cost, Risk, SRE, Effort)"]
    OptimalRank --> Recommendation["Select Recommended Candidate for Proposal"]
```

---

## 3. Cryptographic Human-in-the-Loop State Machine

```mermaid
stateDiagram-v2
    [*] --> DRAFT: Candidate Selected
    DRAFT --> PENDING_APPROVAL: Compute Pre-Mutation SHA-256 & Announce in Switch
    
    PENDING_APPROVAL --> REJECTED: Operator Rejection (Room / UI)
    PENDING_APPROVAL --> EXPIRED: TTL Exceeded (3600s)
    PENDING_APPROVAL --> APPROVED: Authenticated Principal Grants Approval

    APPROVED --> EXECUTING: Valid HMAC Token Presented
    EXECUTING --> VERIFYING: Sandbox Mutation Applied
    
    VERIFYING --> COMPLETED: AST Re-Parsing PASSED & Hashes Match
    VERIFYING --> FAILED_ROLLBACK: Syntax Invalid or Drift Detected
    
    FAILED_ROLLBACK --> ROLLED_BACK: Pre-Mutation Snapshot Restored
    COMPLETED --> [*]: Published to Switch & Logged in SQLite Audit
    REJECTED --> [*]: Halted (Zero Live Cloud Write)
    ROLLED_BACK --> [*]: Audit Recorded
```

---

## 4. Bounded Sandbox Execution Boundary

```
+-------------------------------------------------------------------------------+
|                       SOURCE ENVIRONMENT (COMPLETELY READ-ONLY)               |
|                                                                               |
|   d:\CloudPilot AI\samples\staging                                            |
|   ├── main.tf              (SHA-256: 25e4cbf7... LOCKED PRE-MUTATION)         |
|   └── docker-compose.yml   (SHA-256: 8a4b2c1d... LOCKED PRE-MUTATION)         |
+---------------------------------------+---------------------------------------+
                                        |
                           CLONE TO TEMPORARY DIRECTORY
                                        |
                                        v
+---------------------------------------+---------------------------------------+
|                   ISOLATED WORKSPACE SANDBOX (BOUNDED EXECUTION)             |
|                                                                               |
|   C:\Users\...\AppData\Local\Temp\cloudpilot_sandbox_xyz\                     |
|   ├── main.tf              (Target of AST Attribute Mutation)                 |
|   └── docker-compose.yml   (Target of Compose Resource Limits Mutation)       |
|                                                                               |
|   SAFETY CHECKS:                                                              |
|   1. Pre-execution SHA-256 matches locked proposal hash exactly.             |
|   2. Zero network calls or cloud provider SDK writes allowed.                 |
|   3. terraform apply / pulumi up execution strictly prohibited.              |
|   4. AST re-parsed independently to guarantee 100% syntactically valid code.  |
|   5. If parsing fails, atomic snapshot restores original pre-mutation file.   |
+-------------------------------------------------------------------------------+
```

---

## 5. Switch Protocol Wire Contract

- **WebSocket Handshake:** `GET {bridge_ws}/agents/{agent_id}/connection/ws` with `Authorization: Bearer {token}`
- **Heartbeat & Cursor:** Ping-pong heartbeat with monotonic sequence cursor tracking to prevent lost room messages.
- **Outbound Notifications:** Structured JSON payload delivered to `{bridge_url}/rooms/{room_id}/messages`.
- **Truthful Status Reporting:** Reports `EMULATED_MODE` when local daemon is absent; reports `LIVE_CONNECTED` only upon completed bi-directional remote handshake.

