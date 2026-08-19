"""
Risk Engine Component

Orchestrates the individual risk analyzers (classifier, dependency, blast radius, business impact, policies, root cause, timeline, mitigations)
to compute the unified risk score (0-100) and risk category.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from models_resource import CloudResource
from models_application import Application
from models_risk import RiskAssessment, RiskCategory, ActionType
from risk_classifier import RiskClassifier
from dependency_analyzer import DependencyAnalyzer
from blast_radius import BlastRadiusCalculator
from confidence_engine import ConfidenceEngine
from business_impact import BusinessImpactEvaluator
from policy_engine import PolicyEngine
from root_cause import RootCauseAnalyzer
from timeline_predictor import TimelinePredictor
from mitigation_engine import MitigationEngine

logger = logging.getLogger(__name__)


class RiskEngine:
    """Core reasoning engine that coordinates calculations across all intelligence components."""

    def __init__(
        self,
        classifier: Optional[RiskClassifier] = None,
        dependency_analyzer: Optional[DependencyAnalyzer] = None,
        blast_calculator: Optional[BlastRadiusCalculator] = None,
        confidence_engine: Optional[ConfidenceEngine] = None,
        business_evaluator: Optional[BusinessImpactEvaluator] = None,
        policy_engine: Optional[PolicyEngine] = None,
        root_cause_analyzer: Optional[RootCauseAnalyzer] = None,
        timeline_predictor: Optional[TimelinePredictor] = None,
        mitigation_engine: Optional[MitigationEngine] = None,
    ) -> None:
        """Initialize the Risk Engine with sub-components."""
        self.classifier = classifier or RiskClassifier()
        self.dependency_analyzer = dependency_analyzer or DependencyAnalyzer()
        self.blast_calculator = blast_calculator or BlastRadiusCalculator()
        self.confidence_engine = confidence_engine or ConfidenceEngine()
        self.business_evaluator = business_evaluator or BusinessImpactEvaluator()
        self.policy_engine = policy_engine or PolicyEngine()
        self.root_cause_analyzer = root_cause_analyzer or RootCauseAnalyzer()
        self.timeline_predictor = timeline_predictor or TimelinePredictor()
        self.mitigation_engine = mitigation_engine or MitigationEngine()

        logger.info("RiskEngine initialized successfully")

    def assess_risk(
        self,
        target_id: str,
        resource: Optional[CloudResource],
        application: Optional[Application],
        all_resources: list[CloudResource],
        applications: list[Application],
        service_graph: Any,
        action: ActionType,
        parameters: dict[str, Any],
        historical_incidents: int = 0
    ) -> tuple[RiskAssessment, Any, Any, Any]:
        """Run the comprehensive risk assessment model on the target under action.

        Args:
            target_id: Evaluated resource or application ID
            resource: Specific CloudResource instance (if resource target)
            application: Specific Application instance (if application target or context)
            all_resources: All discovered resources
            applications: All applications
            service_graph: Complete service graph from M3
            action: Simulated action type
            parameters: Action parameters
            historical_incidents: Incident logs count

        Returns:
            Tuple of (RiskAssessment, BlastRadiusReport, ImpactGraph, TimelineDict)
        """
        # Step 1: Resolve cost correlation metrics
        cost_correlation = self.business_evaluator.correlate_cost_and_risk(resource, application, action.value)

        # Step 2: Determine downstream cascade impact paths
        res_id_to_check = target_id
        if not target_id.startswith("res-") and application and application.resource_ids:
            res_id_to_check = application.resource_ids[0]
        
        downstream = self.dependency_analyzer.analyze_downstream_impact(
            res_id_to_check, applications, service_graph
        )

        # Step 3: Run redundancy checks
        redundancy_data = {"has_redundancy": True, "is_spof": False, "failure_probability": 5.0, "state_health_risk": 0.0}
        if resource:
            redundancy_data = self.classifier.evaluate_redundancy_and_health(resource, all_resources)

        # Step 4: Evaluate business impact damage scales
        business_impact = self.business_evaluator.evaluate_impact(
            resource, application, action.value, cost_correlation
        )

        # Step 5: Evaluate organizational policies
        violations = self.policy_engine.evaluate_policies(
            resource, application, action.value, parameters, business_impact.is_business_hours
        )

        # Step 6: Compute final risk score
        risk_score = self._compute_risk_score(
            resource, application, action, redundancy_data, downstream, business_impact, violations, historical_incidents
        )

        # Step 7: Classify risk category
        risk_category = self.classifier.classify_score(risk_score)

        # Step 8: Build blast radius details & impact graph
        blast_report = self.blast_calculator.calculate_blast_radius(
            target_id, applications, service_graph, downstream, cost_correlation
        )
        impact_graph = self.blast_calculator.build_impact_graph(
            target_id, applications, service_graph, blast_report
        )

        # Step 9: Compute confidence scores
        confidence_report = self.confidence_engine.calculate_confidence(
            target_id, resource, application, all_resources, historical_incidents
        )

        # Step 10: Generate root cause analysis and explanations
        explanations = self.root_cause_analyzer.generate_explanation(
            resource, application, action.value, downstream, violations, cost_correlation
        )

        # Step 11: Compute risk timeline prediction details
        timeline = self.timeline_predictor.predict_timeline(
            resource, application, action.value, downstream
        )

        # Step 12: Synthesize mitigation recommendations
        mitigations = self.mitigation_engine.suggest_mitigations(
            resource, application, action.value, violations, downstream
        )

        assessment = RiskAssessment(
            assessment_id=f"risk-{uuid.uuid4().hex[:12]}",
            target_id=target_id,
            action=action,
            risk_score=round(risk_score, 1),
            risk_category=risk_category,
            confidence_score=confidence_report.score.final_score,
            explanation=explanations,
            policy_violations=violations,
            mitigations=mitigations,
            metadata={
                "redundancy": redundancy_data,
                "business_impact": business_impact.dict(),
                "cost_correlation": cost_correlation,
                "confidence_details": confidence_report.score.dict()
            }
        )

        return assessment, blast_report, impact_graph, timeline

    def _compute_risk_score(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: ActionType,
        redundancy_data: dict[str, Any],
        downstream_data: dict[str, Any],
        business_impact: Any,
        policy_violations: list[str],
        historical_incidents: int
    ) -> float:
        """Calculate numerical risk score based on components.

        Components:
        - Health & Redundancy (SPOF)
        - Dependency depth & cascading risk
        - Business impact (Revenue, SLA, customer)
        - Policy violations (Immediate boost to high/critical)
        - Action type inherent riskiness (e.g. TERMINATE is high, START is safe)

        Args:
            resource: Resource
            application: Application
            action: Action
            redundancy_data: Redundancy info
            downstream_data: Cascade info
            business_impact: Impact details
            policy_violations: Active violations
            historical_incidents: incident logs

        Returns:
            Risk score float (0-100)
        """
        score = 10.0  # base risk score

        # Inherent action risk
        action_weights = {
            ActionType.TERMINATE: 40.0,
            ActionType.STOP: 25.0,
            ActionType.RESTART: 20.0,
            ActionType.RESIZE: 15.0,
            ActionType.MODIFY_SECURITY_GROUP: 20.0,
            ActionType.DEPLOY: 15.0,
            ActionType.START: 5.0,
            ActionType.UNKNOWN: 10.0,
        }
        score += action_weights.get(action, 10.0)

        # Health/SPOF risk component
        is_spof = redundancy_data.get("is_spof", True)
        state_health_risk = redundancy_data.get("state_health_risk", 0.0)
        if is_spof and action in (ActionType.TERMINATE, ActionType.STOP):
            score += 15.0
        score += state_health_risk * 0.25

        # Dependency cascade complexity
        dep_score = downstream_data.get("dependency_risk_score", 0.0)
        score += dep_score * 0.35

        # Business damage potential
        business_score = (
            business_impact.revenue_impact_score * 0.4
            + business_impact.customer_impact_score * 0.3
            + business_impact.sla_impact_score * 0.3
        ) * 2.0  # scale to 0-20
        score += business_score

        # Incidents modifier
        score += min(historical_incidents * 3.0, 10.0)

        # Compliance / Policy violations enforce critical/high limits
        if policy_violations:
            score += 40.0

        return min(max(score, 0.0), 100.0)
