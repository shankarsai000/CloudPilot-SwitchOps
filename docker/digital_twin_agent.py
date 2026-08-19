"""
Digital Twin Simulation Agent - Main Orchestrator

Consumes discoveries, cost models, applications, and policies from previous modules.
Creates virtual models representing the cloud environment and simulates proposed modifications.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models_resource import ResourceGraph
from models_application import ApplicationGraph
from models_simulation import DigitalTwin, SimulationReport, ScenarioComparison
from twin_builder import TwinBuilder
from simulator import Simulator
from scenario_engine import ScenarioEngine
from comparison_engine import ComparisonEngine

logger = logging.getLogger(__name__)


class DigitalTwinAgent:
    """Orchestrates virtual REPRESENTATIONS and executes operational/architectural simulations."""

    def __init__(
        self,
        twin_builder: Optional[TwinBuilder] = None,
        simulator: Optional[Simulator] = None,
        scenario_engine: Optional[ScenarioEngine] = None,
        comparison_engine: Optional[ComparisonEngine] = None,
    ) -> None:
        """Initialize the Digital Twin Agent.

        Args:
            twin_builder: Twin Builder instance
            simulator: Simulator instance
            scenario_engine: Scenario Engine instance
            comparison_engine: Comparison Engine instance
        """
        self.twin_builder = twin_builder or TwinBuilder()
        self.simulator = simulator or Simulator()
        self.scenario_engine = scenario_engine or ScenarioEngine()
        self.comparison_engine = comparison_engine or ComparisonEngine()

        # Cache of the active virtual model representing the environment
        self._active_twin: Optional[DigitalTwin] = None
        self._simulation_history: dict[str, SimulationReport] = {}

    def build_twin(
        self,
        resource_graph: ResourceGraph,
        app_graph: ApplicationGraph,
        cost_events: list[Any] = None,
        service_graph: Any = None,
        policies: list[dict[str, Any]] = None
    ) -> DigitalTwin:
        """Construct the virtual twin state representation.

        Args:
            resource_graph: Infrastructure discovery details (M1)
            app_graph: Application boundaries details (M3)
            cost_events: Ingested billing items (M2)
            service_graph: M3 Service Graph
            policies: Configured policies

        Returns:
            DigitalTwin state object
        """
        builder = (
            self.twin_builder
            .with_resources(resource_graph.resources)
            .with_applications(app_graph.applications)
            .with_cost_model(cost_events)
            .with_dependencies(service_graph)
            .with_policies(policies or [])
        )
        self._active_twin = builder.build()
        return self._active_twin

    def get_active_twin(self) -> Optional[DigitalTwin]:
        """Get the active virtual representation.

        Returns:
            DigitalTwin or None
        """
        return self._active_twin

    def run_simulation(
        self,
        target_id: str,
        action: str,
        parameters: Optional[dict[str, Any]] = None,
        policy_violations: list[str] = None
    ) -> Optional[SimulationReport]:
        """Run simulated checks on the active twin state.

        Args:
            target_id: Affected ID
            action: Action simulated
            parameters: Action parameters
            policy_violations: Active policy violations

        Returns:
            SimulationReport or None if twin context has not been built
        """
        if not self._active_twin:
            logger.warning("Simulation aborted: Twin state model has not been constructed.")
            return None

        params = parameters or {}
        report = self.simulator.run_simulation(
            target_id, action, params, self._active_twin, policy_violations
        )
        self._simulation_history[report.simulation_id] = report
        return report

    def simulate_scenario(self, scenario_type: str, target_id: str) -> dict[str, Any]:
        """Execute a custom parameterized scenario simulation.

        Args:
            scenario_type: e.g. DISASTER_RECOVERY
            target_id: Resource/Application ID

        Returns:
            Dict containing simulated outcomes
        """
        return self.scenario_engine.simulate_scenario(scenario_type, target_id, self._active_twin)

    def get_simulation_report(self, simulation_id: str) -> Optional[SimulationReport]:
        """Retrieve historical simulation report.

        Args:
            simulation_id: Simulation identifier

        Returns:
            SimulationReport or None
        """
        return self._simulation_history.get(simulation_id)

    def compare_strategies(
        self,
        target_id: str,
        strategies: list[tuple[str, dict[str, Any]]],
        policy_violations: list[str] = None
    ) -> Optional[ScenarioComparison]:
        """Benchmark candidate strategies side-by-side.

        Args:
            target_id: Target resource/app ID
            strategies: List of (strategy_name, parameter_dict) tuples
            policy_violations: Active violations

        Returns:
            ScenarioComparison details or None
        """
        if not self._active_twin:
            return None

        simulations = {}
        for name, params in strategies:
            # We assume the action type is determined by the strategy name or params (default to RESIZE)
            action = params.get("action", "RESIZE")
            sim_report = self.run_simulation(target_id, action, params, policy_violations)
            if sim_report:
                simulations[name] = sim_report

        # Get base values from resources
        base_cost = 100.0
        base_cpu = 45.0
        res = next((r for r in self._active_twin.resources if r["id"] == target_id), None)
        if res:
            base_cost = res.get("cost_monthly", 100.0)
            base_cpu = res.get("metadata", {}).get("cpu_utilization", 45.0)

        return self.comparison_engine.compare_strategies(target_id, simulations, base_cost, base_cpu)
