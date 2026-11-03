# CloudPilot SwitchOps — Phase 3 Decision Intelligence Engine

## 1. Executive Summary

CloudPilot SwitchOps Phase 3 transforms CloudPilot from a diagnostic infrastructure assessment tool into an **evidence-driven autonomous engineering decision engine**. 

Operating strictly under read-only boundaries (zero uncontrolled mutations, zero live cloud writes, zero float drift), Phase 3 answers ten fundamental engineering questions for every environment:

1. **What changes are possible?** Concrete candidate proposals generated deterministically from Phase 2 assessment findings and declarative infrastructure.
2. **Which changes reduce cost?** Explicit financial models calculating monthly delta spend in USD using Python `Decimal` arithmetic.
3. **Which changes improve security?** Rigorous checks removing public database bindings, stripping privileged containers, and enforcing encryption.
4. **Which changes improve reliability?** SLA protections preserving persistent volumes, mandating multi-AZ failover, and validating healthchecks.
5. **Which changes violate mandatory constraints?** Formal rejection by deterministic rules and the Z3 SMT theorem prover.
6. **Which combinations of changes are feasible?** Candidate interaction detection identifying mutual exclusions, redundancies, and dependencies.
7. **What trade-offs exist between options?** 4-dimensional normalized objective vectors spanning Cost, Security, Reliability, and Simplicity.
8. **Which options are Pareto-optimal?** True multi-objective dominance filtering identifying the non-dominated frontier.
9. **What should CloudPilot recommend, and why?** An authoritative recommendation selected by operator preference profile (`BALANCED`, `COST_FIRST`, `SECURITY_FIRST`, `RELIABILITY_FIRST`) with complete executive rationale.
10. **What evidence supports the recommendation?** Full cryptographic evidence lineage tracing every proposed change back to AST nodes in Terraform (`*.tf`) and Compose (`compose.yaml`).

---

## 2. Core Architecture Pipeline

The decision engine executes as an automated, truth-preserving seven-stage pipeline:

```mermaid
flowchart TD
    A["Phase 2 Assessment & Inventory<br/>(Terraform + Compose)"] --> B["Stage 1: Candidate Generation<br/>(Deterministic Mutation Proposals)"]
    B --> C["Stage 2: Interaction Detection<br/>(Conflicts, Redundancies, Dependencies)"]
    C --> D["Stage 3: Multi-Objective Scoring<br/>(Cost, Security, Reliability, Simplicity)"]
    D --> E["Stage 4: Hard Constraint Engine<br/>(Deterministic Rules + Z3 SMT Solver)"]
    E -->|Rejected Unsafe| F["Rejection Log<br/>(Exclusion Rationale & Evidence)"]
    E -->|Feasible Set| G["Stage 5: Pareto Optimization<br/>(Non-Dominated Set Filtering)"]
    G --> H["Stage 6: Preference Profile Ranking<br/>(Balanced, Cost-First, Sec-First, Rel-First)"]
    H --> I["Stage 7: Recommendation & Lineage Synthesis"]
    I --> J["Switch Team Room Markdown Report"]
    I --> K["SQLite Audit Persistence<br/>(decision_runs, evaluations, reports)"]
```

---

## 3. Seven Operational Stages

### Stage 1: Candidate Generation
- Derives typed candidate modifications directly from Phase 2 findings (`FIN-001`, `FIN-002`, `FIN-003`, `FIN-005`, `SEC-001`..`005`, `REL-001`..`003`).
- Constructs normalized `ProposedChange` contracts specifying exact AST attribute paths, current values, and proposed modifications.
- Synthesizes adversarial candidates (e.g. dropping stateful volumes, exposing database ports to 0.0.0.0/0) to prove hard constraint enforcement.

### Stage 2: Candidate Interaction Detection
- Detects mutually conflicting proposals mutating the same resource attributes (e.g. downscaling vs. upscaling).
- Flags redundant duplicate proposals across specialist agents.
- Records `CandidateInteraction` relations with machine-readable conflict rationale.

### Stage 3: Multi-Objective Objective Scoring
- Evaluates four normalized dimensions on a `[0.0, 100.0]` scale:
  - **Cost Score**: $S_{\text{cost}} = 50.0 + 50.0 \times \frac{\Delta_{\text{savings}}}{\text{Baseline}}$. Higher savings $\rightarrow$ higher score.
  - **Security Score**: Mapped from standard impact levels (`HIGH_POSITIVE` $\rightarrow$ 90, `POSITIVE` $\rightarrow$ 75, `NEUTRAL` $\rightarrow$ 50, `NEGATIVE` $\rightarrow$ 20, `HIGH_NEGATIVE` $\rightarrow$ 5).
  - **Reliability Score**: Mapped from resilience and failover contributions.
  - **Simplicity Score**: Operational ease (`LOW` complexity $\rightarrow$ 100, `MEDIUM` $\rightarrow$ 65, `HIGH` $\rightarrow$ 30).
- Applies explicit uncertainty penalties for unverified assumptions and lower model confidence.

### Stage 4: Constraint Validation & Formal Z3 SMT Verification
- Evaluates hard constraints (`CONST-OPS-01`, `CONST-SEC-01`..`05`, `CONST-REL-01`, `CONST-FIN-01`).
- Translates candidate selection and budget inequalities into first-order logic for the **Z3 SMT Solver** (`z3-solver 5.3.3.0`).
- Validates boolean invariants and outputs formal satisfiability verdicts: `Z3_VERIFIED_SAT`, `Z3_VERIFIED_UNSAT`, or `Z3_FALLBACK`.
- **Fundamental Rule**: Preference profiles can NEVER override a hard constraint.

### Stage 5: Pareto Frontier Optimization
- Implements true Pareto dominance: Candidate $A$ dominates $B$ iff:
  $$\forall d \in \{\text{Cost}, \text{Security}, \text{Reliability}, \text{Simplicity}\}: A_d \ge B_d \quad \land \quad \exists d: A_d > B_d$$
- Partitions candidates into:
  1. **Pareto Optimal**: The non-dominated boundary of feasible trade-offs.
  2. **Dominated**: Feasible candidates surpassed in all dimensions by at least one Pareto optimal candidate.
  3. **Infeasible**: Excluded by hard policy or budget constraints.

### Stage 6: Preference Profile Utility Ranking
- Applies operator-chosen preference profiles to rank candidates exclusively *within* the non-dominated Pareto set:
  - `BALANCED`: Equal weight across all dimensions ($[0.30, 0.25, 0.25, 0.20]$).
  - `COST_FIRST`: Prioritizes immediate OpEx reduction ($[0.55, 0.15, 0.15, 0.15]$).
  - `SECURITY_FIRST`: Prioritizes posture hardening and risk elimination ($[0.15, 0.50, 0.20, 0.15]$).
  - `RELIABILITY_FIRST`: Prioritizes high availability, failover, and uptime ($[0.15, 0.20, 0.50, 0.15]$).

### Stage 7: Recommendation & Switch Room Reporting
- Selects the top-ranked non-dominated candidate as the executive recommendation.
- Formulates a transparent, CTO-grade decision report explaining:
  - Executive recommendation and projected cost savings.
  - Z3 formal verification status.
  - Pareto frontier alternatives and trade-offs.
  - Excluded alternatives and specific constraint violation codes.
  - Next-phase human governance boundaries (Phase 4 approval requirement).
