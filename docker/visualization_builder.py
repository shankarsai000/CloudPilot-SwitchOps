"""
Visualization Builder Component

Renders graph visualizations (EvidenceGraph and Mermaid strings) for dependency, blast radius, and impact paths.
"""

from __future__ import annotations

import logging
from typing import Any
import uuid

from models_explanation import EvidenceGraph, EvidenceNode, EvidenceEdge

logger = logging.getLogger(__name__)


class VisualizationBuilder:
    """Constructs graphs and visual Mermaid flow representations."""

    def __init__(self) -> None:
        """Initialize Visualization Builder."""
        pass

    def build_evidence_graph(
        self,
        decision_id: str,
        evidence: dict[str, Any]
    ) -> EvidenceGraph:
        """Construct the relational EvidenceGraph.

        Args:
            decision_id: Decision ID
            evidence: Gathers evidence parameters

        Returns:
            EvidenceGraph structure
        """
        nodes: list[EvidenceNode] = []
        edges: list[EvidenceEdge] = []

        # Target node
        target_id = evidence.get("resource_id", "target")
        nodes.append(
            EvidenceNode(
                id=target_id,
                label=f"Decision Target ({target_id})",
                source_module="M1",
                value=evidence.get("infrastructure", {}).get("name", target_id)
            )
        )

        # M2 Cost node
        nodes.append(
            EvidenceNode(
                id="node-m2-cost",
                label="Monthly Cost",
                source_module="M2",
                value=f"${evidence.get('cost', {}).get('monthly_cost_estimate', 0.0):.2f}"
            )
        )
        edges.append(EvidenceEdge(source="node-m2-cost", target=target_id))

        # M3 App node
        app_name = evidence.get("application", {}).get("app_name", "Unassigned")
        nodes.append(
            EvidenceNode(
                id="node-m3-app",
                label="Application Boundary",
                source_module="M3",
                value=app_name
            )
        )
        edges.append(EvidenceEdge(source="node-m3-app", target=target_id))

        # M4 Risk node
        risk_cat = evidence.get("risk", {}).get("risk_category", "LOW")
        nodes.append(
            EvidenceNode(
                id="node-m4-risk",
                label="M4 Risk Level",
                source_module="M4",
                value=risk_cat
            )
        )
        edges.append(EvidenceEdge(source="node-m4-risk", target=target_id))

        # M6 Simulation node
        safety_status = evidence.get("simulation", {}).get("safety_status", "Safe")
        nodes.append(
            EvidenceNode(
                id="node-m6-sim",
                label="M6 Safety Status",
                source_module="M6",
                value=safety_status
            )
        )
        edges.append(EvidenceEdge(source="node-m6-sim", target=target_id))

        return EvidenceGraph(nodes=nodes, edges=edges)

    def to_mermaid(self, evidence_graph: EvidenceGraph) -> str:
        """Serialize EvidenceGraph into Mermaid flowchart syntax.

        Args:
            evidence_graph: EvidenceGraph instance

        Returns:
            Mermaid string
        """
        lines = ["graph TD"]
        for node in evidence_graph.nodes:
            # Sanitize nodes for Mermaid
            safe_id = node.id.replace("-", "_").replace(".", "_")
            safe_label = f"{node.label}: {node.value}".replace('"', "'")
            lines.append(f'    {safe_id}["{safe_label} [{node.source_module}]"]')

        for edge in evidence_graph.edges:
            safe_source = edge.source.replace("-", "_").replace(".", "_")
            safe_target = edge.target.replace("-", "_").replace(".", "_")
            lines.append(f"    {safe_source} --> {safe_target}")

        return "\n".join(lines)
