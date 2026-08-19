"""
Business Context Engine — Business criticality calculator.

Calculates composite criticality scores for applications based on
revenue impact, compliance requirements, availability targets,
recovery objectives, and risk analysis from dependency graphs.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models_application import (
    Application,
    BusinessCriticality,
    CriticalityLevel,
    ServiceTier,
)
from service_graph import ServiceGraph

logger = logging.getLogger(__name__)

# Criticality score weights (must sum to 1.0)
WEIGHT_REVENUE: float = 0.25
WEIGHT_COMPLIANCE: float = 0.20
WEIGHT_AVAILABILITY: float = 0.20
WEIGHT_RECOVERY: float = 0.15
WEIGHT_RISK: float = 0.20


class BusinessContextEngine:
    """Calculates business criticality scores for applications.

    Uses a weighted scoring model across five dimensions:
    1. Revenue impact — customer-facing, traffic volume
    2. Compliance impact — regulatory frameworks (PCI, HIPAA, SOC2)
    3. Availability target — SLA commitments
    4. Recovery priority — RTO/RPO requirements
    5. Risk level — dependency complexity, blast radius
    """

    def __init__(self) -> None:
        """Initialize business context engine."""
        logger.info("BusinessContextEngine initialized")

    def calculate_criticality(
        self,
        application: Application,
        service_graph: Optional[ServiceGraph] = None,
    ) -> BusinessCriticality:
        """Calculate business criticality for a single application.

        Args:
            application: Application to assess
            service_graph: Optional service graph for risk analysis

        Returns:
            BusinessCriticality model
        """
        revenue = self._calculate_revenue_impact(application)
        compliance = self._calculate_compliance_impact(application)
        availability = self._calculate_availability_target(application)
        rto, rpo = self._calculate_recovery_objectives(application)
        risk = self._calculate_risk_score(application, service_graph)
        compliance_frameworks = self._extract_compliance_frameworks(application)
        customer_facing = self._is_customer_facing(application)
        data_class = self._classify_data(application)

        # Normalize scores to 0-10 scale
        revenue_score = min(revenue, 10.0)
        compliance_score = min(compliance, 10.0)
        availability_score = self._availability_to_score(availability)
        recovery_score = self._recovery_to_score(rto, rpo)
        risk_score = min(risk, 10.0)

        # Composite criticality score (0-100)
        criticality_score = (
            revenue_score * WEIGHT_REVENUE
            + compliance_score * WEIGHT_COMPLIANCE
            + availability_score * WEIGHT_AVAILABILITY
            + recovery_score * WEIGHT_RECOVERY
            + risk_score * WEIGHT_RISK
        ) * 10  # Scale from 0-10 to 0-100

        # Classify risk level
        risk_level = self._classify_risk_level(criticality_score)

        criticality = BusinessCriticality(
            application_id=application.application_id,
            revenue_impact=round(revenue_score, 1),
            compliance_impact=round(compliance_score, 1),
            availability_target=availability,
            recovery_time_objective_minutes=rto,
            recovery_point_objective_minutes=rpo,
            risk_level=risk_level,
            criticality_score=round(criticality_score, 1),
            compliance_frameworks=compliance_frameworks,
            customer_facing=customer_facing,
            data_classification=data_class,
        )

        # Attach to application
        application.criticality = criticality

        logger.debug(
            "Criticality for %s: score=%.1f, level=%s",
            application.name,
            criticality_score,
            risk_level.value,
        )
        return criticality

    def calculate_all(
        self,
        applications: list[Application],
        service_graph: Optional[ServiceGraph] = None,
    ) -> list[BusinessCriticality]:
        """Calculate criticality for all applications.

        Args:
            applications: Applications to assess
            service_graph: Optional service graph

        Returns:
            List of BusinessCriticality models
        """
        results: list[BusinessCriticality] = []
        for app in applications:
            criticality = self.calculate_criticality(app, service_graph)
            results.append(criticality)

        logger.info(
            "Calculated criticality for %d applications", len(results)
        )
        return results

    def rank_applications(
        self, applications: list[Application]
    ) -> list[Application]:
        """Rank applications by criticality score (highest first).

        Args:
            applications: Applications with criticality already calculated

        Returns:
            Sorted list of applications
        """
        return sorted(
            applications,
            key=lambda a: a.criticality.criticality_score if a.criticality else 0.0,
            reverse=True,
        )

    def _calculate_revenue_impact(self, app: Application) -> float:
        """Calculate revenue impact score (0-10).

        Args:
            app: Application

        Returns:
            Revenue impact score
        """
        score: float = 0.0

        # Customer-facing services have high revenue impact
        if self._is_customer_facing(app):
            score += 5.0

        # Tier-based scoring
        tier_scores: dict[ServiceTier, float] = {
            ServiceTier.TIER_1: 4.0,
            ServiceTier.TIER_2: 2.5,
            ServiceTier.TIER_3: 1.0,
            ServiceTier.TIER_4: 0.5,
            ServiceTier.UNKNOWN: 0.0,
        }
        score += tier_scores.get(app.tier, 0.0)

        # Cost-based boost (from M2 enrichment)
        if app.total_monthly_cost and app.total_monthly_cost > 1000:
            score += min(app.total_monthly_cost / 5000, 1.0)

        return min(score, 10.0)

    def _calculate_compliance_impact(self, app: Application) -> float:
        """Calculate compliance impact score (0-10).

        Args:
            app: Application

        Returns:
            Compliance impact score
        """
        frameworks = self._extract_compliance_frameworks(app)
        if not frameworks:
            return 0.0

        # Each framework adds to the compliance score
        framework_scores: dict[str, float] = {
            "pci-dss": 3.0,
            "hipaa": 3.0,
            "soc2": 2.5,
            "gdpr": 2.5,
            "sox": 2.0,
            "fedramp": 3.0,
            "iso27001": 1.5,
        }

        score: float = 0.0
        for framework in frameworks:
            score += framework_scores.get(framework.lower(), 1.0)

        return min(score, 10.0)

    def _calculate_availability_target(self, app: Application) -> float:
        """Calculate availability SLA target.

        Args:
            app: Application

        Returns:
            Availability target percentage (e.g. 99.99)
        """
        # Check tags for explicit SLA
        sla_tags = ["sla", "SLA", "availability", "uptime"]
        for tag_key in sla_tags:
            sla_value = app.tags.get(tag_key, "")
            if sla_value:
                try:
                    sla = float(sla_value.replace("%", ""))
                    if 90.0 <= sla <= 100.0:
                        return sla
                except (ValueError, AttributeError):
                    pass

        # Default by tier
        tier_defaults: dict[ServiceTier, float] = {
            ServiceTier.TIER_1: 99.99,
            ServiceTier.TIER_2: 99.9,
            ServiceTier.TIER_3: 99.0,
            ServiceTier.TIER_4: 95.0,
            ServiceTier.UNKNOWN: 99.0,
        }
        return tier_defaults.get(app.tier, 99.0)

    def _calculate_recovery_objectives(
        self, app: Application
    ) -> tuple[int, int]:
        """Calculate RTO and RPO.

        Args:
            app: Application

        Returns:
            Tuple of (RTO minutes, RPO minutes)
        """
        # Check tags for explicit RTO/RPO
        rto_value = app.tags.get("rto") or app.tags.get("RTO")
        rpo_value = app.tags.get("rpo") or app.tags.get("RPO")

        if rto_value:
            try:
                rto = int(rto_value)
            except ValueError:
                rto = None
        else:
            rto = None

        if rpo_value:
            try:
                rpo = int(rpo_value)
            except ValueError:
                rpo = None
        else:
            rpo = None

        # Default by tier
        tier_rto: dict[ServiceTier, int] = {
            ServiceTier.TIER_1: 5,
            ServiceTier.TIER_2: 30,
            ServiceTier.TIER_3: 120,
            ServiceTier.TIER_4: 480,
            ServiceTier.UNKNOWN: 60,
        }
        tier_rpo: dict[ServiceTier, int] = {
            ServiceTier.TIER_1: 1,
            ServiceTier.TIER_2: 15,
            ServiceTier.TIER_3: 60,
            ServiceTier.TIER_4: 240,
            ServiceTier.UNKNOWN: 30,
        }

        return (
            rto if rto is not None else tier_rto.get(app.tier, 60),
            rpo if rpo is not None else tier_rpo.get(app.tier, 30),
        )

    def _calculate_risk_score(
        self,
        app: Application,
        service_graph: Optional[ServiceGraph] = None,
    ) -> float:
        """Calculate risk score based on dependencies and complexity.

        Args:
            app: Application
            service_graph: Optional service graph for blast radius analysis

        Returns:
            Risk score (0-10)
        """
        score: float = 0.0

        # Dependency count risk
        dep_count = len(app.dependencies)
        score += min(dep_count * 0.5, 3.0)

        # Resource count complexity
        resource_count = len(app.resource_ids)
        score += min(resource_count * 0.3, 2.0)

        # Blast radius from service graph
        if service_graph:
            for service in app.services:
                blast = service_graph.get_blast_radius(service.service_id)
                score += min(len(blast) * 0.5, 3.0)
                break  # Use first service's blast radius

        # Service count complexity
        service_count = len(app.services)
        score += min(service_count * 0.4, 2.0)

        return min(score, 10.0)

    @staticmethod
    def _availability_to_score(availability: float) -> float:
        """Convert availability percentage to 0-10 score.

        Higher availability targets indicate higher criticality.

        Args:
            availability: Availability target (e.g. 99.99)

        Returns:
            Score 0-10
        """
        if availability >= 99.999:
            return 10.0
        if availability >= 99.99:
            return 9.0
        if availability >= 99.9:
            return 7.0
        if availability >= 99.0:
            return 5.0
        if availability >= 95.0:
            return 3.0
        return 1.0

    @staticmethod
    def _recovery_to_score(rto: int, rpo: int) -> float:
        """Convert RTO/RPO to 0-10 score.

        Lower RTO/RPO indicates higher criticality.

        Args:
            rto: Recovery Time Objective in minutes
            rpo: Recovery Point Objective in minutes

        Returns:
            Score 0-10
        """
        rto_score: float
        if rto <= 5:
            rto_score = 10.0
        elif rto <= 15:
            rto_score = 8.0
        elif rto <= 60:
            rto_score = 6.0
        elif rto <= 240:
            rto_score = 4.0
        else:
            rto_score = 2.0

        rpo_score: float
        if rpo <= 1:
            rpo_score = 10.0
        elif rpo <= 5:
            rpo_score = 8.0
        elif rpo <= 30:
            rpo_score = 6.0
        elif rpo <= 120:
            rpo_score = 4.0
        else:
            rpo_score = 2.0

        return (rto_score + rpo_score) / 2.0

    @staticmethod
    def _classify_risk_level(criticality_score: float) -> CriticalityLevel:
        """Classify risk level from composite score.

        Args:
            criticality_score: Composite score 0-100

        Returns:
            CriticalityLevel enum
        """
        if criticality_score >= 80:
            return CriticalityLevel.CRITICAL
        if criticality_score >= 60:
            return CriticalityLevel.HIGH
        if criticality_score >= 40:
            return CriticalityLevel.MEDIUM
        if criticality_score >= 20:
            return CriticalityLevel.LOW
        return CriticalityLevel.MINIMAL

    @staticmethod
    def _is_customer_facing(app: Application) -> bool:
        """Determine if application is customer-facing.

        Args:
            app: Application

        Returns:
            True if customer-facing
        """
        customer_tags = ["customer-facing", "external", "public"]
        for tag_key in ["visibility", "exposure", "audience", "facing"]:
            value = app.tags.get(tag_key, "").lower()
            if value in customer_tags:
                return True

        # Heuristic: applications with CDN, ALB, or frontend services
        if app.tier == ServiceTier.TIER_1:
            return True

        name_lower = app.name.lower()
        frontend_indicators = ["frontend", "web", "portal", "app", "ui", "gateway", "api"]
        return any(indicator in name_lower for indicator in frontend_indicators)

    @staticmethod
    def _extract_compliance_frameworks(app: Application) -> list[str]:
        """Extract applicable compliance frameworks from tags.

        Args:
            app: Application

        Returns:
            List of compliance framework names
        """
        frameworks: list[str] = []

        compliance_tags = ["compliance", "Compliance", "regulatory", "framework"]
        for tag_key in compliance_tags:
            value = app.tags.get(tag_key, "")
            if value:
                # Comma-separated frameworks
                for framework in value.split(","):
                    cleaned = framework.strip().lower()
                    if cleaned:
                        frameworks.append(cleaned)

        # Check individual framework tags
        framework_checks = ["pci-dss", "hipaa", "soc2", "gdpr", "sox", "fedramp"]
        for framework in framework_checks:
            tag_keys = [framework, framework.upper(), framework.replace("-", "_")]
            for key in tag_keys:
                if app.tags.get(key, "").lower() in ("true", "yes", "1", "enabled"):
                    if framework not in frameworks:
                        frameworks.append(framework)

        return frameworks

    @staticmethod
    def _classify_data(app: Application) -> str:
        """Classify data sensitivity level.

        Args:
            app: Application

        Returns:
            Data classification: public, internal, confidential, restricted
        """
        data_tags = ["data-classification", "data_classification", "DataClassification"]
        for tag_key in data_tags:
            value = app.tags.get(tag_key, "").lower()
            if value in ("public", "internal", "confidential", "restricted"):
                return value

        # Heuristic from compliance
        frameworks = BusinessContextEngine._extract_compliance_frameworks(app)
        if any(f in frameworks for f in ["pci-dss", "hipaa"]):
            return "confidential"
        if any(f in frameworks for f in ["soc2", "gdpr"]):
            return "internal"

        return "internal"
