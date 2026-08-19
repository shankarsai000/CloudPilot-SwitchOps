"""
Roadmap Builder Component

Builds phased optimization roadmaps (e.g. Week 1: Compute -> Week 2: Storage -> Week 3: Networking -> Week 4: Autoscaling)
sorting recommendations chronologically based on dependencies and priorities.
"""

from __future__ import annotations

import logging
from models_strategy import OptimizationPlan, RoadmapPhase

logger = logging.getLogger(__name__)


class RoadmapBuilder:
    """Arranges generated optimization plans into chronological, dependent roadmap phases."""

    def __init__(self) -> None:
        """Initialize Roadmap Builder."""
        pass

    def build_roadmap(self, plans: list[OptimizationPlan]) -> list[RoadmapPhase]:
        """Group and sort optimization plans chronologically.

        Phases:
        - Week 1: Compute & Autoscaling (Fast-wins)
        - Week 2: Storage lifecycle modifications
        - Week 3: Databases & Architecture adjustments
        - Week 4: Network & Governance checks

        Args:
            plans: Calculated Optimization Plans

        Returns:
            List of chronological RoadmapPhase steps
        """
        # Define roadmap buckets
        phase_compute = RoadmapPhase(phase_name="Week 1: Compute & Autoscaling", timeline="Week 1")
        phase_storage = RoadmapPhase(phase_name="Week 2: Storage Optimization", timeline="Week 2")
        phase_databases = RoadmapPhase(phase_name="Week 3: Database & Architecture", timeline="Week 3")
        phase_network = RoadmapPhase(phase_name="Week 4: Networking & Governance", timeline="Week 4")

        # Map categories into phases
        for plan in plans:
            category = plan.roi_analysis.expected_savings_monthly # (dummy check or read plan details)
            # Find category from recommended candidate or description
            cat_str = ""
            for item in plan.execution_blueprint:
                cat_str = item.get("category", "")
                break

            if "COMPUTE" in cat_str or "AUTOSCALING" in cat_str or "CONTAINERS" in cat_str:
                phase_compute.plans.append(plan)
            elif "STORAGE" in cat_str:
                phase_storage.plans.append(plan)
            elif "DATABASES" in cat_str or "ARCHITECTURE" in cat_str:
                phase_databases.plans.append(plan)
            else:
                phase_network.plans.append(plan)

        # Sort recommendations within each phase by savings/ROI (descending)
        for phase in [phase_compute, phase_storage, phase_databases, phase_network]:
            phase.plans.sort(key=lambda p: p.roi_analysis.roi_score, reverse=True)
            # Add dependency trace hints
            for plan in phase.plans:
                phase.dependency_blueprint.append(f"Execute Plan {plan.plan_id} ({plan.recommended_strategy.name})")

        # Only return phases containing plans
        active_phases = [p for p in [phase_compute, phase_storage, phase_databases, phase_network] if len(p.plans) > 0]
        
        # Fallback to single phase if empty context
        if not active_phases and plans:
            phase_compute.plans = plans
            phase_compute.dependency_blueprint = [f"Execute Plan {p.plan_id}" for p in plans]
            active_phases.append(phase_compute)

        logger.info("Roadmap constructed with %d active phases", len(active_phases))
        return active_phases
