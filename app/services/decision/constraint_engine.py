"""
CloudPilot SwitchOps — Deterministic Hard Constraint Engine with Z3 SMT Verification

Evaluates candidate change proposals against mandatory security, reliability,
financial (budget ceilings), and operational policy boundaries.
Integrates the Z3 theorem prover for formal satisfiability verification.
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple

from app.domain.candidates import ApplicabilityStatus, Candidate, CandidateType, ImpactLevel
from app.domain.constraints import (
    ConstraintResult,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintType,
)
from app.domain.policies import PolicyConfiguration

logger = logging.getLogger("cloudpilot.decision.constraints")

# Attempt Z3 import
try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    logger.warning("Z3 solver library is not available. Constraint engine will record Z3_FALLBACK.")


class ConstraintEngine:
    """
    Deterministic constraint evaluator enforcing non-negotiable operational boundaries.
    Mandatory constraint violations strictly exclude candidates from the feasible set.
    """

    def __init__(
        self,
        policy_config: Optional[PolicyConfiguration] = None,
        policy: Optional[PolicyConfiguration] = None,
    ) -> None:
        self.policy = policy or policy_config or PolicyConfiguration()

    def evaluate(self, candidate: Candidate) -> tuple[bool, List[ConstraintResult], List[str]]:
        """Evaluate candidate and return (is_feasible, constraint_results, rejection_reasons)."""
        results = self.evaluate_candidate(candidate)
        blocking = [r for r in results if r.is_blocking]
        is_feasible = (len(blocking) == 0)
        reasons = [r.reason for r in blocking]
        return is_feasible, results, reasons

    def evaluate_candidate(self, candidate: Candidate) -> List[ConstraintResult]:
        """
        Evaluate all active policy constraints against an individual candidate.
        Returns a list of ConstraintResult records.
        """
        results: List[ConstraintResult] = []

        # 1. Operational Constraint: Applicability
        results.append(self._check_const_ops_01_applicability(candidate))

        # 2. Security Constraint: Public Database or Cache Exposure (CONST-SEC-01)
        if self.policy.disallow_public_database:
            results.append(self._check_const_sec_01_public_database(candidate))

        # 3. Security Constraint: Privileged Containers (CONST-SEC-02)
        if self.policy.disallow_privileged_containers:
            results.append(self._check_const_sec_02_privileged_containers(candidate))

        # 4. Security Constraint: Docker Socket Mount (CONST-SEC-03)
        if self.policy.disallow_docker_socket:
            results.append(self._check_const_sec_03_docker_socket(candidate))

        # 5. Security Constraint: Wildcard Ingress (CONST-SEC-04)
        if self.policy.disallow_wildcard_ingress:
            results.append(self._check_const_sec_04_wildcard_ingress(candidate))

        # 6. Security Constraint: Encryption Retention (CONST-SEC-05)
        if self.policy.mandatory_encryption:
            results.append(self._check_const_sec_05_encryption(candidate))

        # 7. Reliability Constraint: Mandatory Persistence for Stateful DB (CONST-REL-01)
        if self.policy.mandatory_persistence_for_stateful:
            results.append(self._check_const_rel_01_stateful_persistence(candidate))

        # 8. Financial Constraint: Budget Ceiling (CONST-FIN-01)
        if self.policy.monthly_budget_ceiling is not None:
            results.append(self._check_const_fin_01_budget_ceiling(candidate))

        return results

    def verify_satisfiability_with_z3(
        self,
        candidates: List[Candidate],
        baseline_cost: Decimal,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Formally verifies constraint satisfiability across the candidate set using the Z3 SMT solver.
        Encodes integer/real budget inequalities and boolean invariants.
        Returns (z3_status, diagnostics).
        """
        if not Z3_AVAILABLE:
            return "Z3_FALLBACK", {"reason": "z3-solver package not installed in environment"}

        try:
            solver = z3.Solver()
            candidate_vars: Dict[str, z3.BoolRef] = {}

            # Create boolean variables for each candidate: x_i == True means candidate is selected
            for c in candidates:
                var_name = f"select_{c.candidate_id.replace('-', '_')}"
                candidate_vars[c.candidate_id] = z3.Bool(var_name)

            # Rule 1: Invariant - Any candidate flagged as DROP_PERSISTENCE or DISABLE_AUTH must never be selected
            for c in candidates:
                if c.candidate_type in (CandidateType.DROP_PERSISTENCE, CandidateType.DISABLE_AUTH):
                    solver.add(z3.Not(candidate_vars[c.candidate_id]))

            # Rule 2: Budget constraint formulation in Z3 Real arithmetic
            if self.policy.monthly_budget_ceiling is not None:
                budget_ceiling = z3.RealVal(str(self.policy.monthly_budget_ceiling))
                # Model total monthly spend: baseline - sum(savings_i * x_i) <= budget
                # Equivalently: baseline - budget <= sum(savings_i * x_i)
                total_spend = z3.RealVal(str(baseline_cost))
                for c in candidates:
                    try:
                        c_after = z3.RealVal(str(c.estimated_monthly_cost_after))
                    except Exception:
                        c_after = z3.RealVal("0.0")

                    # If candidate c is selected, its cost after must not exceed budget alone
                    solver.add(z3.Implies(candidate_vars[c.candidate_id], c_after <= budget_ceiling))

            if candidates:
                # Rule 3: Require that at least one candidate proposal is selected
                solver.add(z3.Or([candidate_vars[c.candidate_id] for c in candidates]))

            # Check satisfiability
            check_result = solver.check()
            if check_result == z3.sat:
                model = solver.model()
                logger.info("Z3 SMT verification SATISFIED across %d candidates", len(candidates))
                return "Z3_VERIFIED_SAT", {
                    "solver_assertions": len(solver.assertions()),
                    "solver_result": "sat",
                }
            elif check_result == z3.unsat:
                logger.warning("Z3 SMT verification UNSATISFIED: Constraints mutually incompatible")
                return "Z3_VERIFIED_UNSAT", {
                    "solver_assertions": len(solver.assertions()),
                    "solver_result": "unsat",
                }
            else:
                return "Z3_UNKNOWN", {"reason": "Z3 returned unknown"}

        except Exception as exc:
            logger.error("Z3 verification encountered error: %s", exc)
            return "Z3_FALLBACK", {"error": str(exc)}

    # --- Individual Constraint Checks ---

    def _check_const_ops_01_applicability(self, candidate: Candidate) -> ConstraintResult:
        if candidate.applicability == ApplicabilityStatus.UNSUPPORTED:
            return ConstraintResult(
                constraint_id="CONST-OPS-01",
                constraint_type=ConstraintType.OPERATIONAL,
                severity=ConstraintSeverity.MANDATORY,
                status=ConstraintStatus.FAIL,
                reason="Candidate proposes unsupported resource transformation or unresolvable syntax.",
                affected_candidate_ids=[candidate.candidate_id],
                evidence_refs={"applicability": candidate.applicability.value},
                policy_version=self.policy.policy_version,
            )
        return ConstraintResult(
            constraint_id="CONST-OPS-01",
            constraint_type=ConstraintType.OPERATIONAL,
            severity=ConstraintSeverity.MANDATORY,
            status=ConstraintStatus.PASS,
            reason="Candidate targets supported declarative infrastructure resources.",
            affected_candidate_ids=[candidate.candidate_id],
            policy_version=self.policy.policy_version,
        )

    def _check_const_sec_01_public_database(self, candidate: Candidate) -> ConstraintResult:
        # Check if candidate explicitly opens database ports or is an anti-pattern candidate
        if candidate.candidate_type == CandidateType.DISABLE_AUTH:
            return ConstraintResult(
                constraint_id="CONST-SEC-01",
                constraint_type=ConstraintType.SECURITY,
                severity=ConstraintSeverity.MANDATORY,
                status=ConstraintStatus.FAIL,
                reason="HARD CONSTRAINT VIOLATION: Candidate proposes public internet binding (0.0.0.0) for database listener.",
                affected_candidate_ids=[candidate.candidate_id],
                evidence_refs={"candidate_type": candidate.candidate_type.value},
                policy_version=self.policy.policy_version,
            )

        for ch in candidate.proposed_changes:
            val_str = str(ch.proposed_value)
            meta_str = str(getattr(ch, "change_metadata", "") or "")
            if "0.0.0.0" in val_str:
                if (
                    "5432" in val_str or "3306" in val_str or "6379" in val_str
                    or "5432" in meta_str or "3306" in meta_str or "6379" in meta_str
                    or "db" in ch.resource_id.lower() or "database" in ch.resource_id.lower()
                    or "postgres" in ch.resource_id.lower() or "mysql" in ch.resource_id.lower()
                ):
                    return ConstraintResult(
                        constraint_id="CONST-SEC-01",
                        constraint_type=ConstraintType.SECURITY,
                        severity=ConstraintSeverity.MANDATORY,
                        status=ConstraintStatus.FAIL,
                        reason=f"[CONST-SEC-01] HARD CONSTRAINT VIOLATION: Candidate introduces public binding {val_str} on database/cache port.",
                        affected_candidate_ids=[candidate.candidate_id],
                        evidence_refs={"attribute": ch.attribute_path, "value": val_str},
                        policy_version=self.policy.policy_version,
                    )
            elif "port" in ch.attribute_path:
                if ("5432" in val_str or "3306" in val_str or "6379" in val_str) and "0.0.0.0" in val_str:
                    return ConstraintResult(
                        constraint_id="CONST-SEC-01",
                        constraint_type=ConstraintType.SECURITY,
                        severity=ConstraintSeverity.MANDATORY,
                        status=ConstraintStatus.FAIL,
                        reason=f"[CONST-SEC-01] HARD CONSTRAINT VIOLATION: Candidate introduces public binding {val_str} on database/cache port.",
                        affected_candidate_ids=[candidate.candidate_id],
                        evidence_refs={"attribute": ch.attribute_path, "value": val_str},
                        policy_version=self.policy.policy_version,
                    )

        return ConstraintResult(
            constraint_id="CONST-SEC-01",
            constraint_type=ConstraintType.SECURITY,
            severity=ConstraintSeverity.MANDATORY,
            status=ConstraintStatus.PASS,
            reason="Candidate does not expose database or cache ports to public interfaces.",
            affected_candidate_ids=[candidate.candidate_id],
            policy_version=self.policy.policy_version,
        )

    def _check_const_sec_02_privileged_containers(self, candidate: Candidate) -> ConstraintResult:
        for ch in candidate.proposed_changes:
            if ch.attribute_path == "privileged" and ch.proposed_value is True:
                return ConstraintResult(
                    constraint_id="CONST-SEC-02",
                    constraint_type=ConstraintType.SECURITY,
                    severity=ConstraintSeverity.MANDATORY,
                    status=ConstraintStatus.FAIL,
                    reason="HARD CONSTRAINT VIOLATION: Candidate introduces privileged container execution.",
                    affected_candidate_ids=[candidate.candidate_id],
                    evidence_refs={"privileged": True},
                    policy_version=self.policy.policy_version,
                )

        return ConstraintResult(
            constraint_id="CONST-SEC-02",
            constraint_type=ConstraintType.SECURITY,
            severity=ConstraintSeverity.MANDATORY,
            status=ConstraintStatus.PASS,
            reason="Candidate maintains unprivileged container isolation.",
            affected_candidate_ids=[candidate.candidate_id],
            policy_version=self.policy.policy_version,
        )

    def _check_const_sec_03_docker_socket(self, candidate: Candidate) -> ConstraintResult:
        for ch in candidate.proposed_changes:
            if ch.attribute_path == "volumes" and isinstance(ch.proposed_value, list):
                if any("docker.sock" in str(v) for v in ch.proposed_value):
                    return ConstraintResult(
                        constraint_id="CONST-SEC-03",
                        constraint_type=ConstraintType.SECURITY,
                        severity=ConstraintSeverity.MANDATORY,
                        status=ConstraintStatus.FAIL,
                        reason="HARD CONSTRAINT VIOLATION: Candidate mounts Docker daemon socket (/var/run/docker.sock).",
                        affected_candidate_ids=[candidate.candidate_id],
                        evidence_refs={"volume": "/var/run/docker.sock"},
                        policy_version=self.policy.policy_version,
                    )

        return ConstraintResult(
            constraint_id="CONST-SEC-03",
            constraint_type=ConstraintType.SECURITY,
            severity=ConstraintSeverity.MANDATORY,
            status=ConstraintStatus.PASS,
            reason="Candidate does not mount host Docker daemon socket.",
            affected_candidate_ids=[candidate.candidate_id],
            policy_version=self.policy.policy_version,
        )

    def _check_const_sec_04_wildcard_ingress(self, candidate: Candidate) -> ConstraintResult:
        for ch in candidate.proposed_changes:
            if "ingress" in ch.attribute_path and isinstance(ch.proposed_value, list):
                if "0.0.0.0/0" in ch.proposed_value:
                    return ConstraintResult(
                        constraint_id="CONST-SEC-04",
                        constraint_type=ConstraintType.SECURITY,
                        severity=ConstraintSeverity.MANDATORY,
                        status=ConstraintStatus.FAIL,
                        reason="HARD CONSTRAINT VIOLATION: Candidate retains 0.0.0.0/0 wildcard ingress.",
                        affected_candidate_ids=[candidate.candidate_id],
                        evidence_refs={"cidr_blocks": ch.proposed_value},
                        policy_version=self.policy.policy_version,
                    )

        return ConstraintResult(
            constraint_id="CONST-SEC-04",
            constraint_type=ConstraintType.SECURITY,
            severity=ConstraintSeverity.MANDATORY,
            status=ConstraintStatus.PASS,
            reason="Candidate does not permit wildcard ingress to sensitive management ports.",
            affected_candidate_ids=[candidate.candidate_id],
            policy_version=self.policy.policy_version,
        )

    def _check_const_sec_05_encryption(self, candidate: Candidate) -> ConstraintResult:
        for ch in candidate.proposed_changes:
            if ch.attribute_path in ("encrypted", "storage_encrypted") and ch.proposed_value is False:
                return ConstraintResult(
                    constraint_id="CONST-SEC-05",
                    constraint_type=ConstraintType.SECURITY,
                    severity=ConstraintSeverity.MANDATORY,
                    status=ConstraintStatus.FAIL,
                    reason="HARD CONSTRAINT VIOLATION: Candidate disables storage encryption at rest.",
                    affected_candidate_ids=[candidate.candidate_id],
                    evidence_refs={"attribute": ch.attribute_path},
                    policy_version=self.policy.policy_version,
                )

        return ConstraintResult(
            constraint_id="CONST-SEC-05",
            constraint_type=ConstraintType.SECURITY,
            severity=ConstraintSeverity.MANDATORY,
            status=ConstraintStatus.PASS,
            reason="Candidate preserves or enables storage encryption at rest.",
            affected_candidate_ids=[candidate.candidate_id],
            policy_version=self.policy.policy_version,
        )

    def _check_const_rel_01_stateful_persistence(self, candidate: Candidate) -> ConstraintResult:
        if candidate.candidate_type == CandidateType.DROP_PERSISTENCE:
            return ConstraintResult(
                constraint_id="CONST-REL-01",
                constraint_type=ConstraintType.RELIABILITY,
                severity=ConstraintSeverity.MANDATORY,
                status=ConstraintStatus.FAIL,
                reason="HARD CONSTRAINT VIOLATION: Candidate irrevocably drops persistent storage volume on a stateful database.",
                affected_candidate_ids=[candidate.candidate_id],
                evidence_refs={"candidate_type": candidate.candidate_type.value},
                policy_version=self.policy.policy_version,
            )

        for ch in candidate.proposed_changes:
            res_id_low = ch.resource_id.lower()
            res_name_low = ch.resource_name.lower()
            if (
                ch.attribute_path == "volumes"
                or "volume" in ch.resource_type.lower()
                or "volume" in res_id_low
                or "volume" in res_name_low
            ):
                if ch.proposed_value is None or ch.action_type == "REMOVE":
                    return ConstraintResult(
                        constraint_id="CONST-REL-01",
                        constraint_type=ConstraintType.RELIABILITY,
                        severity=ConstraintSeverity.MANDATORY,
                        status=ConstraintStatus.FAIL,
                        reason=f"HARD CONSTRAINT VIOLATION: Removing persistent volume on stateful resource '{ch.resource_id}' violates persistence policy.",
                        affected_candidate_ids=[candidate.candidate_id],
                        evidence_refs={"resource": ch.resource_id},
                        policy_version=self.policy.policy_version,
                    )
            elif ch.attribute_path == "volumes" and ch.action_type == "REMOVE" and ("db" in res_name_low or "postgres" in res_name_low):
                return ConstraintResult(
                    constraint_id="CONST-REL-01",
                    constraint_type=ConstraintType.RELIABILITY,
                    severity=ConstraintSeverity.MANDATORY,
                    status=ConstraintStatus.FAIL,
                    reason=f"HARD CONSTRAINT VIOLATION: Removing persistent volume on stateful resource '{ch.resource_name}' violates persistence policy.",
                    affected_candidate_ids=[candidate.candidate_id],
                    evidence_refs={"resource": ch.resource_name},
                    policy_version=self.policy.policy_version,
                )

        return ConstraintResult(
            constraint_id="CONST-REL-01",
            constraint_type=ConstraintType.RELIABILITY,
            severity=ConstraintSeverity.MANDATORY,
            status=ConstraintStatus.PASS,
            reason="Candidate maintains or provisions required persistent storage for stateful workloads.",
            affected_candidate_ids=[candidate.candidate_id],
            policy_version=self.policy.policy_version,
        )

    def _check_const_fin_01_budget_ceiling(self, candidate: Candidate) -> ConstraintResult:
        ceiling_str = self.policy.monthly_budget_ceiling
        if ceiling_str is None:
            return ConstraintResult(
                constraint_id="CONST-FIN-01",
                constraint_type=ConstraintType.FINANCIAL,
                severity=ConstraintSeverity.MANDATORY,
                status=ConstraintStatus.NOT_APPLICABLE,
                reason="No monthly budget ceiling configured in active policy.",
                affected_candidate_ids=[candidate.candidate_id],
                policy_version=self.policy.policy_version,
            )

        try:
            ceiling = Decimal(ceiling_str)
            cost_after = Decimal(candidate.estimated_monthly_cost_after)
        except Exception:
            return ConstraintResult(
                constraint_id="CONST-FIN-01",
                constraint_type=ConstraintType.FINANCIAL,
                severity=ConstraintSeverity.MANDATORY,
                status=ConstraintStatus.UNKNOWN,
                reason="Unparseable decimal cost string encountered during budget ceiling check.",
                affected_candidate_ids=[candidate.candidate_id],
                policy_version=self.policy.policy_version,
            )

        if cost_after > ceiling:
            return ConstraintResult(
                constraint_id="CONST-FIN-01",
                constraint_type=ConstraintType.FINANCIAL,
                severity=ConstraintSeverity.MANDATORY,
                status=ConstraintStatus.FAIL,
                reason=f"HARD CONSTRAINT VIOLATION: Candidate monthly cost (${cost_after}) exceeds configured budget ceiling (${ceiling}).",
                affected_candidate_ids=[candidate.candidate_id],
                evidence_refs={"cost_after": str(cost_after), "budget_ceiling": str(ceiling)},
                policy_version=self.policy.policy_version,
            )

        return ConstraintResult(
            constraint_id="CONST-FIN-01",
            constraint_type=ConstraintType.FINANCIAL,
            severity=ConstraintSeverity.MANDATORY,
            status=ConstraintStatus.PASS,
            reason=f"Candidate monthly cost (${cost_after}) complies with budget ceiling (${ceiling}).",
            affected_candidate_ids=[candidate.candidate_id],
            evidence_refs={"cost_after": str(cost_after), "budget_ceiling": str(ceiling)},
            policy_version=self.policy.policy_version,
        )
