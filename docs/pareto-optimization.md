# CloudPilot SwitchOps — Multi-Objective Pareto & Bounded Combination Optimization

## 1. Mathematical Formulation

CloudPilot models infrastructure decision-making as a 4-dimensional vector optimization problem across individual candidate proposals and bounded multi-candidate change bundles:

$$\max \vec{f}(c) = \begin{bmatrix} f_{\text{cost}}(c) \\ f_{\text{security}}(c) \\ f_{\text{reliability}}(c) \\ f_{\text{simplicity}}(c) \end{bmatrix} \quad \text{subject to } c \in \mathcal{F}$$

where:
- $\mathcal{F}$ is the set of feasible candidates (including both atomic and composite candidates) that satisfy all mandatory policy constraints (`CONST-OPS-01`, `CONST-SEC-*`, `CONST-REL-*`, `CONST-FIN-01`).
- All objective functions $f_d(c) \in [0.0, 100.0]$ are strictly normalized and clamped such that **higher values always represent superior engineering outcomes**.

---

## 2. Bounded Combination Optimization ($k \le 3$)

In Phase 3.1, CloudPilot evaluates both individual candidates and **bounded multi-candidate combinations** (`COMPOSITE_PLAN`).

### Scope and Guarantees
- **Bounded Search Ceiling**: Maximum combination size is explicitly constrained to $k \le 3$. The engine explicitly records:
  $$\text{optimization\_scope} = \text{"BOUNDED\_COMBINATION (k=3)"}$$
  It never claims exhaustive global search across combinatorial state spaces.
- **Deterministic Enumeration**: Combinations of sizes $k \in \{2, 3\}$ are enumerated deterministically via sorted `itertools.combinations`.
- **Attribute Conflict Rejection**: Combinations containing candidate pairs that propose contradictory mutations to the exact same resource attribute are pruned upfront.
- **Dependency Closure**: If candidate $A$ depends on $B$ (`DEPENDENT`), combination $S$ is only valid if $B \in S$.
- **Decimal Financial Aggregation**: Combined monthly savings and post-change spend are computed with exact Python `Decimal` arithmetic.
- **Monotonic Risk Composition**:
  - Security and reliability impacts propagate pessimistically: if any component has negative impact, the combined plan inherits the negative rating.
  - Operational complexity takes the maximum complexity among member changes.

---

## 3. Pareto Dominance Definition

Candidate $A$ **dominates** candidate $B$ ($A \succ B$) if and only if:
1. $A$ is at least as good as $B$ in all 4 dimensions:
   $$\forall d \in \{\text{Cost}, \text{Security}, \text{Reliability}, \text{Simplicity}\}: f_d(A) \ge f_d(B)$$
2. $A$ is strictly better than $B$ in at least one dimension:
   $$\exists d \in \{\text{Cost}, \text{Security}, \text{Reliability}, \text{Simplicity}\}: f_d(A) > f_d(B)$$

### The Pareto Frontier $\mathcal{P}$
$$\mathcal{P} = \{ c \in \mathcal{F} \mid \nexists c' \in \mathcal{F}: c' \succ c \}$$

Candidates on $\mathcal{P}$ represent the set of optimal engineering trade-offs where improving any single dimension necessitates sacrificing another. Both atomic candidates and composite plans compete on equal mathematical footing across $\mathcal{P}$.

---

## 4. Preference Profile Weighting

Preference profiles are applied strictly to rank candidates **within** the Pareto frontier $\mathcal{P}$:

$$U(c, P) = \sum_{d} w_{d}(P) \times f_d(c)$$

| Preference Profile | Cost Weight ($w_{\text{cost}}$) | Security Weight ($w_{\text{sec}}$) | Reliability Weight ($w_{\text{rel}}$) | Simplicity Weight ($w_{\text{simp}}$) |
| :--- | :---: | :---: | :---: | :---: |
| `BALANCED` | 0.30 | 0.30 | 0.25 | 0.15 |
| `COST_FIRST` | **0.60** | 0.15 | 0.15 | 0.10 |
| `SECURITY_FIRST` | 0.10 | **0.60** | 0.20 | 0.10 |
| `RELIABILITY_FIRST` | 0.15 | 0.15 | **0.55** | 0.15 |

*Note*: If an invalid or unrecognized profile is requested, the system safely falls back to `BALANCED`.

---

## 5. Invariant Guarantees

1. **Anti-Dominated Invariant**: A dominated candidate $B$ can never be recommended over a candidate $A$ that dominates it, regardless of preference profile weights.
2. **Constraint Primacy**: An infeasible candidate violating a hard constraint can never enter $\mathcal{P}$ regardless of weights.
3. **Formal Invariant Verification**: All candidates on the frontier have their satisfiability verified by Z3 SMT solver or deterministic rules.
