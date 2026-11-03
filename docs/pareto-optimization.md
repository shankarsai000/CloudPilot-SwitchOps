# CloudPilot SwitchOps — Multi-Objective Pareto Optimization

## 1. Mathematical Formulation

CloudPilot models infrastructure decision-making as a 4-dimensional vector optimization problem:

$$\max \vec{f}(c) = \begin{bmatrix} f_{\text{cost}}(c) \\ f_{\text{security}}(c) \\ f_{\text{reliability}}(c) \\ f_{\text{simplicity}}(c) \end{bmatrix} \quad \text{subject to } c \in \mathcal{F}$$

where:
- $\mathcal{F}$ is the set of feasible candidates that passed all hard constraints (`CONST-OPS-01`, `CONST-SEC-*`, `CONST-REL-*`, `CONST-FIN-01`).
- All objective functions $f_d(c) \in [0.0, 100.0]$ are strictly normalized such that **higher values represent superior engineering outcomes**.

---

## 2. Pareto Dominance Definition

Candidate $A$ **dominates** candidate $B$ ($A \succ B$) if and only if:
1. $A$ is at least as good as $B$ in all 4 dimensions:
   $$\forall d \in \{\text{Cost}, \text{Security}, \text{Reliability}, \text{Simplicity}\}: f_d(A) \ge f_d(B)$$
2. $A$ is strictly better than $B$ in at least one dimension:
   $$\exists d \in \{\text{Cost}, \text{Security}, \text{Reliability}, \text{Simplicity}\}: f_d(A) > f_d(B)$$

### The Pareto Frontier $\mathcal{P}$
$$\mathcal{P} = \{ c \in \mathcal{F} \mid \nexists c' \in \mathcal{F}: c' \succ c \}$$

Candidates on $\mathcal{P}$ represent the set of optimal engineering trade-offs where improving any single dimension necessitates sacrificing another.

---

## 3. Preference Profile Weighting

Preference profiles are applied strictly to rank candidates **within** the Pareto frontier $\mathcal{P}$:

$$U(c, P) = \sum_{d} w_{d}(P) \times f_d(c)$$

| Preference Profile | Cost Weight ($w_{\text{cost}}$) | Security Weight ($w_{\text{sec}}$) | Reliability Weight ($w_{\text{rel}}$) | Simplicity Weight ($w_{\text{simp}}$) |
| :--- | :---: | :---: | :---: | :---: |
| `BALANCED` | 0.30 | 0.25 | 0.25 | 0.20 |
| `COST_FIRST` | **0.55** | 0.15 | 0.15 | 0.15 |
| `SECURITY_FIRST` | 0.15 | **0.50** | 0.20 | 0.15 |
| `RELIABILITY_FIRST` | 0.15 | 0.20 | **0.50** | 0.15 |

---

## 4. Invariant Guarantees

1. **Anti-Dominated Invariant**: A dominated candidate $B$ can never be recommended over a candidate $A$ that dominates it, regardless of the preference profile weights.
2. **Constraint Primacy**: An infeasible candidate violating a hard constraint can never enter $\mathcal{P}$ regardless of weights.
