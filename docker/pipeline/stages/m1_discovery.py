"""
Stage 1: M1 Infrastructure Discovery Stage.
Pipes simulated enterprise cloud topology into canonical ResourceGraph.
"""

from __future__ import annotations

from typing import Dict
from collections import Counter

from models_resource import ResourceGraph
from pipeline.models import StageResult, StageStatus, UnifiedExecutionContext
from pipeline.stages.base import BasePipelineStage
from simulator.adapters import SimulatedCloudAdapter


class M1DiscoveryStage(BasePipelineStage):
    """
    Stage 1: Discovers all cloud assets and network dependencies from the active simulator.
    """
    stage_id = "m1_discovery"
    stage_name = "M1 Infrastructure Discovery"
    is_critical = True

    def __init__(self, adapter: SimulatedCloudAdapter = None) -> None:
        super().__init__(is_critical=True, max_retries=1)
        self.adapter = adapter or SimulatedCloudAdapter()

    def _run(self, context: UnifiedExecutionContext) -> StageResult:
        # Run discovery via simulated cloud adapter
        resources, edges = self.adapter.discover()

        by_type: Dict[str, int] = Counter(r.type.value if hasattr(r.type, 'value') else str(r.type) for r in resources)
        by_prov: Dict[str, int] = Counter(r.provider for r in resources)

        resource_graph = ResourceGraph(
            resources=resources,
            dependencies=edges,
            total_resources=len(resources),
            resources_by_type=dict(by_type),
            resources_by_provider=dict(by_prov),
            failures=[],
        )

        context.infrastructure_state = resource_graph

        evidence = {
            "total_resources": len(resources),
            "total_dependencies": len(edges),
            "resource_types": dict(by_type),
            "providers": dict(by_prov),
        }

        return StageResult(
            stage_id=self.stage_id,
            stage_name=self.stage_name,
            status=StageStatus.COMPLETED,
            confidence=100.0,
            input_summary={"scenario": context.scenario_name, "scale": context.scale, "seed": context.seed},
            output_summary={"discovered_resources": len(resources), "dependencies": len(edges)},
            evidence=evidence,
        )
