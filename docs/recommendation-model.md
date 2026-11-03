# CloudPilot SwitchOps — Recommendation Model & Traceability Lineage

## 1. Recommendation Synthesis

The Recommendation Engine (`RecommendationEngine`) bridges quantitative optimization algorithms and human-readable engineering rationale. It compiles:

1. **Executive Recommendation**: The top-ranked candidate from the Pareto frontier $\mathcal{P}$ under the active preference profile.
2. **Impact Delta**: Direct comparison of monthly OpEx before and after adoption, with exact Decimal currency precision.
3. **Trade-Off Analysis**: Transparent documentation explaining what is gained (e.g., $110/mo savings) versus what is compromised (e.g., lower peak compute burst headroom).
4. **Alternatives Menu**: Non-dominated alternatives on the Pareto frontier for engineering evaluation.
5. **Rejection Audit**: Explicit list of excluded candidates along with their failed constraint rule identifiers.

---

## 2. Switch Room Presentation Format

In the Switch team room, CloudPilot posts structured markdown:

```markdown
## 🧠 [CloudPilot SwitchOps] Decision Intelligence & Optimization Report
- **Decision ID**: `dec-8e2b19cf` | **Status**: `COMPLETED`
- **Target Workspace**: `samples/staging`
- **Preference Profile**: `BALANCED`
- **Z3 Formal Constraint Verification**: `Z3_VERIFIED_SAT`
- **Candidate Pool**: 7 generated | **5 feasible** | **2 rejected** by hard constraints

### 1. Executive Recommendation
**Downsize Web Server Compute** (`cand-fin-003-ec2`)
- **Monthly Impact**: Before: `$147.20` → After: `$36.80` (**Savings: $110.40/mo**)
- **Security**: `NEUTRAL` | **Reliability**: `NEUTRAL` | **Complexity**: `LOW`
- **Key Action**: Downsize instance_type from t3.xlarge to t3.medium in samples/staging/main.tf

### 2. Pareto Frontier & Alternatives (4 Non-Dominated)
- `Downsize Web Server Compute` ⭐ [RECOMMENDED]: **$110.40/mo** savings | Scores: Cost=76, Sec=50, Rel=50
- `Enable Multi-AZ Database Failover`: **-$45.00/mo** spend | Scores: Cost=39, Sec=50, Rel=90
- `Restrict Public Ingress`: **$0.00/mo** savings | Scores: Cost=50, Sec=85, Rel=50

### 3. Rejected Alternatives (2 Excluded by Hard Constraints)
- ❌ `Drop Persistent Volume to Reduce Disk Cost`: **REJECTED** ([CONST-REL-01] Stateful persistence violated)
- ❌ `Expose Database to Avoid NAT Gateway Spend`: **REJECTED** ([CONST-SEC-01] Public DB binding disallowed)

### 4. Next Phase Governance
- Changes are proposed in read-only analysis mode.
- In Phase 4, human approval in this Switch room will be required before applying any change plan.

*Full decision audit trail recorded with provenance referencing Assessment `asm-c284e1b7`.*
```

---

## 3. Evidence Lineage & Provenance

Every decision report records a complete `evidence_lineage` dictionary:
- `task_id`: Identifier of the originating Switch task.
- `assessment_id`: Identifier of the underlying Phase 2 assessment.
- `workspace_root`: Target filesystem root scanned during discovery.
- `pricing_catalog_version`: FinOps catalog schema version.
- `policy_version`: Policy invariants and budget threshold version.
- `z3_verification_status`: Cryptographic/formal satisfiability record from Z3.
