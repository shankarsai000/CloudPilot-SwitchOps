# CloudPilot SwitchOps — Constraint Engine & Formal Z3 Verification

## 1. Overview

The Constraint Engine (`ConstraintEngine`) serves as the authoritative, non-negotiable gatekeeper of CloudPilot SwitchOps. It prevents any candidate proposal that introduces security vulnerabilities, data loss risks, or budget overruns from reaching the Pareto optimization frontier.

**Core Axiom**: Preference profiles (`COST_FIRST`, `BALANCED`, etc.) can NEVER override or bypass a hard constraint.

---

## 2. Hard Constraint Catalog

| Constraint ID | Category | Enforcement Mode | Policy Rule | Violation Outcome |
| :--- | :--- | :--- | :--- | :--- |
| `CONST-OPS-01` | Operational | Deterministic Rule | Candidate must target supported, resolvable infrastructure resources. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-01` | Security | Deterministic + Z3 | Database listeners (`5432`, `3306`, `6379`) must not be bound to `0.0.0.0/0`. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-02` | Security | Deterministic + Z3 | Containers must not run with `privileged: true` capabilities. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-03` | Security | Deterministic + Z3 | Containers must not mount host `/var/run/docker.sock`. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-04` | Security | Deterministic + Z3 | Management ports (`22`, `3389`) must not retain wildcard `0.0.0.0/0` ingress. | Immediate rejection (`INFEASIBLE`) |
| `CONST-SEC-05` | Security | Deterministic + Z3 | Storage encryption at rest must not be disabled. | Immediate rejection (`INFEASIBLE`) |
| `CONST-REL-01` | Reliability | Deterministic + Z3 | Stateful database workloads must not have persistent storage removed. | Immediate rejection (`INFEASIBLE`) |
| `CONST-FIN-01` | Financial | Deterministic + Z3 | Projected monthly spend must not exceed `monthly_budget_ceiling`. | Immediate rejection (`INFEASIBLE`) |

---

## 3. Formal Z3 SMT Theorem Prover Integration

Beyond heuristic rules, CloudPilot uses Microsoft's **Z3 SMT Solver** (`z3-solver 5.3.3.0`) for formal mathematical satisfiability verification.

### Mathematical Formulation
1. **Selection Indicators**: Boolean variable $x_i \in \{0, 1\}$ for each candidate $c_i \in C$, where $x_i = \text{True}$ denotes candidate inclusion in the final change plan.
2. **Mandatory Invariants Encoding**: For any candidate $c_i$ violating an active mandatory policy invariant (`CONST-OPS-01`, `CONST-SEC-01..05`, `CONST-REL-01`):
   $$\neg x_i$$
3. **Mutual Exclusions & Interactions**:
   - For all pairwise conflicts $(c_a, c_b)$ modifying the same resource attribute contradictorily:
     $$\neg (x_a \land x_b)$$
   - For all redundant duplicate candidate pairs $(c_a, c_b)$:
     $$\neg (x_a \land x_b)$$
4. **Dependency Implications**: For any candidate $c_{\text{dep}}$ requiring prerequisite parent $c_{\text{parent}}$:
   $$x_{\text{dep}} \implies x_{\text{parent}}$$
5. **Real-Arithmetic Budget Inequalities**: If monthly budget ceiling $B$ is configured:
   $$\forall i: x_i \implies \text{cost\_after}_i \le B$$
6. **Candidate Selection Semantics**: When non-empty candidate proposals are presented:
   $$\bigvee_{i=1}^n x_i$$

### Standardized Solver Status Codes
- `Z3_CONSTRAINTS_SAT`: The encoded mandatory security invariants, persistence requirements, budget inequalities, and mutual exclusion rules are formally satisfiable.
  > **Formal Semantics Note**: `SAT` proves satisfiability of the *encoded mathematical constraints*; it is not a proof of global runtime safety or system optimality.
- `Z3_CONSTRAINTS_UNSAT`: The encoded constraints are mutually contradictory; no candidate satisfies all invariants, budget ceilings, and interaction exclusions simultaneously.
- `Z3_UNKNOWN`: Solver timed out or could not prove satisfiability within configured timeout boundaries.
- `Z3_UNAVAILABLE`: The native `z3-solver` package is not available in the execution environment; truth-preserving fallback is reported without faking SAT.
- `RULE_ENGINE_VALIDATED`: Verification was performed via deterministic rule evaluation when solver was intentionally bypassed or candidate pool was empty.

---

## 4. Aggregate Combination Budget Verification & Fail-Closed Guarantees

Phase 3.2 establishes rigorous release-gate verifications across composite change plans and solver semantics:

### Aggregate Budget Invariant
- **Individual vs. Composite Feasibility**: An individual candidate $c_1$ ($80/mo) and $c_2$ ($70/mo) may each satisfy a budget ceiling ($100/mo) in isolation. However, their bounded composite plan $C = c_1 + c_2$ ($150/mo) strictly violates the ceiling and is rejected with `is_feasible = False`.
- **Decimal Precision**: All cost aggregation is executed using Python `Decimal` arithmetic rounded to 2 decimal places (`ROUND_HALF_UP`) to prevent IEEE-754 binary floating point precision drift.
- **Double-Counting Prevention**: When multiple candidates modify the same resource on different attributes, the resource's baseline OpEx is registered once by resource ID.
- **Fail-Closed Unknown Pricing**: If any candidate or composite member has missing, corrupted, or unparseable pricing data, `CONST-FIN-01` returns `ConstraintStatus.UNKNOWN` with `is_blocking = True`. In Z3, unparseable pricing is strictly asserted as $\neg x_i$ rather than defaulting to $0.00.

### Decoded Model Defensive Verification
When Z3 returns `sat`, the solver model is defensively decoded:
1. Every candidate ID in `selected_sample` is checked against `rejected_by_invariant`. If any invariant-violating candidate is present in the model, an exception is raised.
2. Mutually exclusive or conflicting candidates in `selected_sample` are checked against candidate interactions. If more than one conflicting candidate is selected, an exception is raised.
This guarantees the solver can never return an incomplete or invalid candidate combination.
