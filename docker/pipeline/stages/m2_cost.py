"""
Stage 2: M2 Cost Intelligence Stage.
Ingests billing lines, correlates spend to M1 resources, detects anomalies, and forecasts trends.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from cost_agent import CostIntelligenceAgent
from pipeline.models import CostStageOutput, StageResult, StageStatus, UnifiedExecutionContext
from pipeline.stages.base import BasePipelineStage
from simulator.adapters import SimulatedBillingAdapter


class M2CostStage(BasePipelineStage):
    """
    Stage 2: Correlates cloud billing line items to discovered infrastructure and forecasts costs.
    """
    stage_id = "m2_cost"
    stage_name = "M2 Cost Intelligence"
    is_critical = True

    def __init__(self, billing_adapter: SimulatedBillingAdapter = None) -> None:
        super().__init__(is_critical=True, max_retries=1)
        self.billing_adapter = billing_adapter or SimulatedBillingAdapter()

    def _run(self, context: UnifiedExecutionContext) -> StageResult:
        res_graph = context.infrastructure_state
        if not res_graph:
            raise ValueError("M2 requires M1 infrastructure_state in context")

        # Map resources into dict for CostCorrelator
        resource_dict: Dict[str, Dict[str, Any]] = {
            r.id: {
                "name": r.name,
                "type": r.type.value if hasattr(r.type, 'value') else str(r.type),
                "provider": r.provider,
                "region": r.region,
                "tags": r.tags,
                "owner": r.owner,
            }
            for r in res_graph.resources
        }

        agent = CostIntelligenceAgent(resources=resource_dict)

        # Fetch billing items from simulated billing adapter
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=30)
        end_date = now

        line_items = self.billing_adapter.fetch_billing_data(start_date=start_date, end_date=end_date)
        date_str = now.strftime("%Y-%m-%d")

        # Process and correlate line items to resources
        cost_events = agent.process_billing_data(line_items, date_str)

        # Detect anomalies
        anomalies = agent.detect_anomalies(cost_events)

        # Forecast costs
        forecasts = agent.forecast_costs(cost_events, days=30)

        total_spend = sum(item.cost_amount for item in line_items)

        cost_output = CostStageOutput(
            billing_items=line_items,
            cost_events=cost_events,
            anomalies=anomalies,
            forecasts=forecasts,
            total_monthly_spend_usd=round(total_spend, 2),
        )
        context.costs = cost_output

        evidence = {
            "total_monthly_spend_usd": round(total_spend, 2),
            "billing_line_items_count": len(line_items),
            "cost_events_count": len(cost_events),
            "anomalies_detected": len(anomalies),
            "forecast_days_ahead": 30,
        }

        return StageResult(
            stage_id=self.stage_id,
            stage_name=self.stage_name,
            status=StageStatus.COMPLETED,
            confidence=95.0,
            input_summary={"m1_resources_count": len(res_graph.resources)},
            output_summary={
                "total_monthly_spend_usd": round(total_spend, 2),
                "anomalies": len(anomalies),
                "forecasts": len(forecasts),
            },
            evidence=evidence,
        )
