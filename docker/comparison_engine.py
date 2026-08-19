"""
Comparison Engine Component

Compares multiple candidate strategies side-by-side to highlight the best option.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from models_simulation import ScenarioComparison, SimulationReport

logger = logging.getLogger(__name__)


class ComparisonEngine:
    """Benchmarking component to compare multiple simulated strategies."""

    def __init__(self) -> None:
        """Initialize Comparison Engine."""
        pass

    def compare_strategies(
        self,
        target_id: str,
        simulations: dict[str, SimulationReport],
        base_cost: float = 1000.0,
        base_cpu: float = 30.0
    ) -> ScenarioComparison:
        """Benchmark candidate simulations and select the best recommended option.

        Args:
            target_id: Target resource/app ID
            simulations: Dictionary mapping strategy name -> SimulationReport
            base_cost: Current baseline cost
            base_cpu: Current baseline CPU

        Returns:
            ScenarioComparison object
        """
        # Determine recommended strategy based on safety score and expected monthly savings
        best_strategy = "Current State"
        best_score = -1.0

        for name, sim in simulations.items():
            # Scoring logic: higher expected savings + higher safety score = better choice
            savings = sim.cost.monthly_savings_usd
            safety = sim.safety_score
            score = (savings * 0.5) + (safety * 0.5)
            
            # Penalize unsafe strategies
            if sim.safety_status == "Unsafe":
                score -= 50.0

            if score > best_score:
                best_score = score
                best_strategy = name

        trade_offs = []
        for name, sim in simulations.items():
            trade_offs.append(
                f"Strategy '{name}' saves ${sim.cost.monthly_savings_usd:.2f}/mo with safety score of {sim.safety_score:.1f} ({sim.safety_status})."
            )
        trade_off_text = " ".join(trade_offs) + f" Recommended strategy: '{best_strategy}'."

        return ScenarioComparison(
            comparison_id=f"comp-{uuid.uuid4().hex[:12]}",
            target_id=target_id,
            base_state={
                "monthly_cost": base_cost,
                "cpu_utilization": base_cpu
            },
            simulations=simulations,
            recommended_strategy_name=best_strategy,
            trade_off_analysis=trade_off_text
        )
