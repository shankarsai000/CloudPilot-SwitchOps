# CloudPilot SwitchOps — Constraint Engine & Formal Z3 Verification

## 1. Overview

The Constraint Engine (`ConstraintEngine`) serves as the authoritative, non-negotiable gatekeeper of CloudPilot SwitchOps. It prevents any candidate proposal that introduces security vulnerabilities, data loss risks, or budget overruns from reaching the Pareto optimization frontier.

**Core Axiom**: Preference profiles (`COST_FIRST`, `BALANCED`, etc.) can NEVER override or bypass a hard constraint.

---

## 2. Hard Constraint Catalog

| Constraint ID | Category | Enforcement Mode | Policy Rule | Violation Outcome |
| :--- | :--- | :--- | :--- | :--- |
| `CONST-OPS-01` | Operational | Deterministic Rule | Candidate must target supported, resolvable infrastructure resources. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-01` | Security | Deterministic Rule | Database listeners (`5432`, `3306`, `6379`) must not be bound to `0.0.0.0/0`. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-02` | Security | Deterministic Rule | Containers must not run with `privileged: true` capabilities. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-03` | Security | Deterministic Rule | Containers must not mount host `/var/run/docker.sock`. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-04` | Security | Deterministic Rule | Management ports (`22`, `3389`) must not retain wildcard `0.0.0.0/0` ingress. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-05` | Security | Deterministic Rule | Storage encryption at rest must not be disabled. | Immediate rejection (`INFEASIBLE`) |
| `CONST-REL-01` | Reliability | Deterministic Rule | Stateful database workloads must not have persistent storage removed. | Immediate rejection (`INFEASIBLE`) |
| `CONST-FIN-01` | Financial | Deterministic + Z3 | Projected monthly spend must not exceed `monthly_budget_ceiling`. | Immediate rejection (`INFEASIBLE`) |

---

## 3. Formal Z3 SMT Theorem Prover Integration

Beyond heuristic rules, CloudPilot uses Microsoft's **Z3 SMT Solver** (`z3-solver 5.3.3.0`) for formal mathematical verification.

### Encoding Logic
1. **Selection Variables**: Boolean indicator variable $x_i \in \{0, 1\}$ for each candidate $c_i$.
2. **Anti-pattern Invariants**: For any candidate marked as `DROP_PERSISTENCE` or `DISABLE_AUTH`:
   $$\neg x_i$$
3. **Selection Requirement**: At least one candidate must be chosen:
   $$\bigvee_{i=1}^n x_i$$
4. **Real-Arithmetic Budget Inequalities**: If monthly budget ceiling $B$ is defined:
   $$\forall i: x_i \implies \text{cost\_after}_i \le B$$

### Status Reporting
- `Z3_VERIFIED_SAT`: Proven mathematically satisfiable by Z3. A feasible solution exists that satisfies all invariants.
- `Z3_VERIFIED_UNSAT`: Proven unsatisfiable by Z3. The budget ceiling or invariants are mutually contradictory.
- `Z3_FALLBACK`: Graceful degradation if the native Z3 binary is unavailable in a sandboxed host environment.
