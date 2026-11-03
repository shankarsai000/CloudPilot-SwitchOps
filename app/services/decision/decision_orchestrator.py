"""
CloudPilot SwitchOps — Decision Intelligence Orchestrator

Coordinates the full Phase 3 decision pipeline:
1. Loads Phase 2 inventory and assessment findings.
2. Generates candidate changes.
3. Performs candidate interaction and compatibility checks.
4. Evaluates multi-objective scores.
5. Validates hard constraints with deterministic rules and Z3 SMT solver.
6. Calculates genuine Pareto frontier and applies preference ranking.
7. Produces transparent explanations and recommendations.
8. Persists decision runs and reports to the repository.
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.errors import NotFoundError, ValidationError
from app.domain.candidates import Candidate
from app.domain.decisions import DecisionReport, DecisionRun
from app.domain.objectives import PreferenceProfile
from app.domain.policies import PolicyConfiguration
from app.persistence.repository import TaskRepositoryInterface
from app.services.decision.candidate_evaluator import CandidateEvaluator
from app.services.decision.candidate_generator import CandidateGenerator
from app.services.decision.combination_optimizer import CombinationOptimizer
from app.services.decision.constraint_engine import ConstraintEngine
from app.services.decision.objective_calculator import ObjectiveCalculator
from app.services.decision.pareto_optimizer import ParetoOptimizer
from app.services.decision.recommendation_engine import RecommendationEngine

logger = logging.getLogger("cloudpilot.decision.orchestrator")


class DecisionOrchestrator:
    """
    Main entry point for executing autonomous decision intelligence workflows.
    """

    def __init__(
        self,
        repository: TaskRepositoryInterface,
        candidate_generator: Optional[CandidateGenerator] = None,
        constraint_engine: Optional[ConstraintEngine] = None,
        objective_calculator: Optional[ObjectiveCalculator] = None,
        pareto_optimizer: Optional[ParetoOptimizer] = None,
        recommendation_engine: Optional[RecommendationEngine] = None,
        combination_optimizer: Optional[CombinationOptimizer] = None,
    ) -> None:
        self.repository = repository
        self.generator = candidate_generator or CandidateGenerator()
        self.constraint_engine = constraint_engine or ConstraintEngine()
        self.objective_calculator = objective_calculator or ObjectiveCalculator()
        self.evaluator = CandidateEvaluator(
            constraint_engine=self.constraint_engine,
            objective_calculator=self.objective_calculator,
        )
        self.optimizer = pareto_optimizer or ParetoOptimizer(
            objective_calculator=self.objective_calculator,
        )
        self.recommender = recommendation_engine or RecommendationEngine()
        self.combination_optimizer = combination_optimizer or CombinationOptimizer(max_combination_size=3)

    def run_decision_analysis(
        self,
        task_id: str,
        preference_profile: PreferenceProfile = PreferenceProfile.BALANCED,
        policy_config: Optional[PolicyConfiguration] = None,
        include_adversarial_test_candidates: bool = True,
        enable_combination_optimization: bool = True,
    ) -> Tuple[DecisionRun, DecisionReport]:
        """
        Executes end-to-end decision intelligence on an existing task's assessment and inventory.
        Evaluates both individual candidates and bounded candidate combinations (k <= 3).
        """
        policy = policy_config or PolicyConfiguration()
        # Update constraint engine with current policy
        self.constraint_engine.policy = policy
        self.evaluator.constraint_engine.policy = policy

        # 1. Retrieve Phase 2 Assessment and Discovered Inventory
        assessment = self.repository.get_assessment_for_task(task_id)
        if not assessment:
            raise NotFoundError(
                f"No assessment summary found for task '{task_id}'. Run Phase 2 assessment before decision analysis.",
                resource_type="assessment",
                resource_id=task_id,
            )

        inventory = self.repository.get_inventory_for_task(task_id)
        if not inventory:
            raise NotFoundError(
                f"No discovered inventory found for task '{task_id}'.",
                resource_type="inventory",
                resource_id=task_id,
            )

        findings = self.repository.get_findings_for_task(task_id)
        baseline_cost = Decimal(assessment.estimated_monthly_cost)

        # Update objective calculator baseline
        self.objective_calculator.baseline_monthly_cost = baseline_cost

        # 2. Generate Candidate Changes
        candidates = self.generator.generate_candidates(
            inventory=inventory,
            findings=findings,
            policy_config=policy,
            include_adversarial_test_candidates=include_adversarial_test_candidates,
        )
        logger.info("Generated %d base candidate changes for task '%s'", len(candidates), task_id)

        # 3. Detect Candidate Interactions / Conflicts
        interactions = self.evaluator.detect_interactions(candidates)

        # 3b. Generate Bounded Multi-Candidate Combinations (k <= 3)
        candidate_pool: List[Candidate] = list(candidates)
        if enable_combination_optimization and len(candidates) >= 2:
            composite_plans = self.combination_optimizer.generate_valid_combinations(
                candidates=candidates,
                interactions=interactions,
            )
            candidate_pool.extend(composite_plans)
            logger.info("Generated %d bounded composite candidate plans", len(composite_plans))

        # 4. Evaluate Candidates (Hard Constraints & Multi-Objective Scores)
        evaluations = self.evaluator.evaluate_all(candidate_pool)

        # 5. Formal Z3 SMT Constraint Verification
        z3_status, z3_diag = self.constraint_engine.verify_satisfiability_with_z3(
            candidates=candidate_pool,
            baseline_cost=baseline_cost,
            interactions=interactions,
        )

        # 6. Genuine Pareto Frontier Calculation & Preference Ranking
        pareto_optimal, dominated, rejected = self.optimizer.calculate_pareto_frontier(
            evaluations=evaluations,
            preference_profile=preference_profile,
        )

        # 7. Synthesize Recommendation & Report
        decision_run, report = self.recommender.build_decision_run(
            task_id=task_id,
            assessment_id=assessment.assessment_id,
            workspace_root=inventory.workspace_root,
            policy_config=policy,
            preference_profile=preference_profile,
            pareto_optimal=pareto_optimal,
            dominated=dominated,
            rejected=rejected,
            interactions=interactions,
            z3_status=z3_status,
        )

        # 8. Persist Decision Run, Evaluations, Interactions, and Report to Repository
        self.repository.save_decision_run(decision_run)
        self.repository.save_candidate_evaluations(
            decision_id=decision_run.decision_id,
            evaluations=evaluations,
        )
        self.repository.save_interactions(
            decision_id=decision_run.decision_id,
            interactions=interactions,
        )
        self.repository.save_decision_report(report)

        logger.info(
            "Decision run '%s' completed and persisted: %d Pareto optimal, %d rejected",
            decision_run.decision_id,
            decision_run.pareto_optimal_count,
            decision_run.rejected_candidates_count,
        )

        return decision_run, report
