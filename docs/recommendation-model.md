# CloudPilot SwitchOps — Recommendation Model & Evidence Provenance

## 1. Recommendation Synthesis

The Recommendation Engine (`RecommendationEngine`) bridges quantitative optimization algorithms and human-readable engineering rationale. It compiles:

1. **Executive Recommendation**: The top-ranked non-dominated candidate or composite plan from the Pareto frontier $\mathcal{P}$ under the active preference profile.
2. **Impact Delta**: Direct comparison of monthly OpEx before and after adoption, with exact `Decimal` currency precision.
3. **Trade-Off Analysis**: Transparent documentation explaining what is gained (e.g., $110/mo savings) versus what is compromised (e.g., lower peak compute burst headroom).
4. **Alternatives Menu**: Non-dominated alternatives on the Pareto frontier for engineering evaluation.
5. **Rejection Audit**: Explicit list of excluded candidates along with their failed constraint rule identifiers.
6. **Evidence Provenance & SHA-256 Digest**: Immutable hash verifying the exact inputs, findings, and policies producing the decision.

---

## 2. Switch Room Presentation Format

In the Switch team room, CloudPilot posts structured markdown:

```markdown
## 🧠 [CloudPilot SwitchOps] Decision Intelligence & Optimization Report
- **Decision ID**: `dec-8e2b19cf` | **Status**: `COMPLETED`
- **Target Workspace**: `samples/staging`
- **Preference Profile**: `BALANCED`
- **Optimization Scope**: `BOUNDED_COMBINATION (k=3)`
- **Z3 Formal Constraint Verification**: `Z3_CONSTRAINTS_SAT`
- **Provenance SHA-256**: `a4f89d1b63e2c940`
- **Candidate Pool**: 74 generated | **65 feasible** | **9 rejected** by hard constraints

### 1. Executive Recommendation
**Composite Plan (2 changes): Enable KMS encryption + Rightsize EC2** (`comb-b534274e`)
- **Monthly Impact**: Before: `$147.20` → After: `$92.30` (**Savings: $54.90/mo**)
- **Security**: `HIGH_POSITIVE` | **Reliability**: `NEUTRAL` | **Complexity**: `LOW`
- **Key Action**: Bounded combination of 2 compatible candidates.

### 2. Pareto Frontier & Alternatives (15 Non-Dominated)
- `Composite Plan (2 changes)` ⭐ [RECOMMENDED]: **$54.90/mo** savings | Scores: Cost=63, Sec=89, Rel=49
- `Rightsize EC2 'staging_web'`: **$54.90/mo** savings | Scores: Cost=63, Sec=49, Rel=49
- `Attach persistent named volume to 'postgres'`: **$0.00/mo** savings | Scores: Cost=49, Sec=49, Rel=89

### 3. Rejected Alternatives (9 Excluded by Hard Constraints)
- ❌ `Drop Persistent Volume to Reduce Disk Cost`: **REJECTED** ([CONST-REL-01] Stateful persistence violated)
- ❌ `Expose Database to Avoid NAT Gateway Spend`: **REJECTED** ([CONST-SEC-01] Public DB binding disallowed)

### 4. Next Phase Governance
- Changes are proposed in read-only analysis mode.
- In Phase 4, human approval in this Switch room will be required before applying any change plan.

*Full decision audit trail recorded with evidence provenance referencing Assessment `asm-c284e1b7` (SHA-256: `a4f89d1b63e2c940`).*
```

---

## 3. Evidence Provenance & Cryptographic Verification

Phase 3.1 replaces informal "cryptographic lineage" descriptions with an exact, independently reproducible **Evidence Provenance Architecture**.

### Provenance Inputs
The provenance payload contains the complete set of immutable decision inputs:
- `task_id`: Identifier of the originating Switch room task.
- `assessment_id`: Identifier of the underlying Phase 2 assessment.
- `workspace_root`: Target filesystem root scanned during discovery.
- `pricing_catalog_version`: FinOps catalog schema version (e.g. `"1.0"`).
- `policy_version`: Policy invariants and budget threshold version (e.g. `"1.0"`).
- `objective_model_version`: Multi-objective model scoring version (`"1.1"`).
- `optimization_scope`: Explicit bounded combinatorial scope (`"BOUNDED_COMBINATION (k=3)"`).
- `z3_verification_status`: Formal satisfiability verdict from the Z3 SMT solver.
- `pareto_optimal_candidate_ids`: Deterministically sorted IDs of non-dominated candidates.
- `source_finding_ids`: Deterministically sorted finding IDs originating the proposals.
- `affected_resource_ids`: Deterministically sorted resource IDs impacted by proposals.
- `source_files`: Deterministically sorted declarative files declaring mutations.

### SHA-256 Digest Computation
```python
def compute_provenance_hash(provenance_data: Dict[str, Any]) -> str:
    clean_data = {k: v for k, v in provenance_data.items() if k != "provenance_hash"}
    canonical_bytes = json.dumps(clean_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
```

### Independent Verification Utility
Any third-party verifier or CI gate can independently verify provenance using:
```python
from app.services.decision.recommendation_engine import verify_report_provenance

is_intact = verify_report_provenance(report)
# Returns True if genuine; returns False if any finding, policy, or score was tampered with
```

---

## 4. Phase 4 Execution Safety Preconditions & Trust Boundary Disclosure

### Phase 4 Safety Preconditions Checklist
Before Phase 4 Human-in-the-Loop Approval and Bounded Execution can execute any modification, the execution runtime requires and validates:
1. **DecisionRun ID**: Globally unique run identifier (`decision_id`).
2. **Selected Candidate Proposal**: Explicit atomic candidate or composite plan (`recommended_candidate`).
3. **Canonical Proposal Representation**: Deterministic, typed list of proposed resource mutations (`proposed_changes`).
4. **Proposal Hash (`proposal_hash`)**: Cryptographic SHA-256 digest over the canonical JSON representation of sorted mutations.
5. **Source Evidence & Affected Resources**: Traceable finding references (`source_finding_ids`) and affected infrastructure resource IDs (`affected_resource_ids`).
6. **Policy & Pricing Catalog Versions**: Explicit versions recorded for reproducible evaluation (`policy_version`, `pricing_catalog_version`).
7. **Constraint Verification Verdict**: Formal Z3 status (`Z3_CONSTRAINTS_SAT`) and individual rule passing statuses.
8. **Explicit Optimization Scope**: Explicit bounded scope (`BOUNDED_COMBINATION (k=3)`).
9. **Rejected Alternatives Audit**: Complete list of infeasible candidates with specific violated constraint IDs and reasons (`rejected_candidates`).

### Local SQLite Trust Boundary Honest Disclosure
- **In-Flight & Audit Integrity**: The SHA-256 `provenance_hash` and `proposal_hash` provide deterministic tamper detection against accidental data corruption, communication tampering, or unauthorized runtime modifications between decision generation and human approval.
- **Storage Boundary**: CloudPilot SwitchOps persists decision records and reports into SQLite (`cloudpilot.db`). Because SQLite is a local file-based database without an external Hardware Security Module (HSM), KMS-backed asymmetric signature, or immutable public transparency log (e.g., Sigstore Rekor), an administrator with direct filesystem write access to the SQLite database file could alter both the report and the stored hash.
- **Production Hardening**: For enterprise production environments requiring non-repudiation, the trust boundary should be anchored to an external HSM, KMS digital signatures, or an append-only transparency ledger.
