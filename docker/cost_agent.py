"""
Cost Intelligence Agent - Main Orchestrator
Parallel billing ingestion, correlation, anomaly detection, forecasting
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor

from models_cost import (
    BillingLineItem, CostEvent, CostAnomaly, CostForecast,
    CostProvider, CostByTeam
)
from aws_billing_adapter import AWSBillingAdapter
from azure_billing_adapter import AzureBillingAdapter
from gcp_billing_adapter import GCPBillingAdapter
from cost_correlator import CostCorrelator
from anomaly_detector import AnomalyDetector
from cost_forecaster import CostForecaster

logger = logging.getLogger(__name__)


class CostIntelligenceAgent:
    """Main Cost Intelligence Agent orchestrator."""
    
    def __init__(
        self,
        aws_config: Optional[Dict[str, Any]] = None,
        azure_config: Optional[Dict[str, Any]] = None,
        gcp_config: Optional[Dict[str, Any]] = None,
        resources: Optional[Dict[str, Dict]] = None
    ) -> None:
        """
        Initialize Cost Intelligence Agent.
        
        Args:
            aws_config: AWS configuration dict
            azure_config: Azure configuration dict
            gcp_config: GCP configuration dict
            resources: M1 resources for correlation
        """
        self.aws_adapter: Optional[AWSBillingAdapter] = None
        self.azure_adapter: Optional[AzureBillingAdapter] = None
        self.gcp_adapter: Optional[GCPBillingAdapter] = None
        self.correlator = CostCorrelator(resources)
        self.anomaly_detector = AnomalyDetector()
        self.forecaster = CostForecaster()
        
        self._init_adapters(aws_config, azure_config, gcp_config)
        
        logger.info("Cost Intelligence Agent initialized")
    
    def _init_adapters(
        self,
        aws_config: Optional[Dict[str, Any]],
        azure_config: Optional[Dict[str, Any]],
        gcp_config: Optional[Dict[str, Any]]
    ) -> None:
        """Initialize cloud adapters."""
        if aws_config:
            try:
                self.aws_adapter = AWSBillingAdapter(
                    region=aws_config.get('region', 'us-east-1'),
                    profile_name=aws_config.get('profile_name')
                )
                logger.debug("AWS adapter initialized")
            except Exception as e:
                logger.warning("Failed to initialize AWS adapter: %s", str(e))
        
        if azure_config:
            try:
                self.azure_adapter = AzureBillingAdapter(
                    subscription_id=azure_config.get('subscription_id', ''),
                    tenant_id=azure_config.get('tenant_id')
                )
                logger.debug("Azure adapter initialized")
            except Exception as e:
                logger.warning("Failed to initialize Azure adapter: %s", str(e))
        
        if gcp_config:
            try:
                self.gcp_adapter = GCPBillingAdapter(
                    project_id=gcp_config.get('project_id', ''),
                    dataset_id=gcp_config.get('dataset_id', 'billing_export')
                )
                logger.debug("GCP adapter initialized")
            except Exception as e:
                logger.warning("Failed to initialize GCP adapter: %s", str(e))
    
    def update_resources(self, resources: Dict[str, Dict]) -> None:
        """
        Update M1 resources for correlation.
        
        Args:
            resources: Dict of resource_id -> metadata
        """
        self.correlator.update_resources(resources)
        logger.info("Updated resources: %d total", len(resources))
    
    def ingest_billing_data(
        self,
        start_date: datetime,
        end_date: datetime,
        accounts: Optional[Dict[str, str]] = None
    ) -> List[BillingLineItem]:
        """
        Ingest billing data from all configured providers (parallel).
        
        Args:
            start_date: Start of billing period
            end_date: End of billing period
            accounts: Dict of provider -> account_id
            
        Returns:
            List of BillingLineItem objects
        """
        all_items: List[BillingLineItem] = []
        accounts = accounts or {}
        
        logger.info("Starting billing data ingestion (%s to %s)", 
                   start_date.date(), end_date.date())
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            
            # AWS
            if self.aws_adapter and 'aws' in accounts:
                future = executor.submit(
                    self.aws_adapter.get_billing_data,
                    start_date, end_date, accounts['aws']
                )
                futures['aws'] = future
            
            # Azure
            if self.azure_adapter and 'azure' in accounts:
                future = executor.submit(
                    self.azure_adapter.get_billing_data,
                    start_date, end_date
                )
                futures['azure'] = future
            
            # GCP
            if self.gcp_adapter and 'gcp' in accounts:
                future = executor.submit(
                    self.gcp_adapter.get_billing_data,
                    start_date, end_date
                )
                futures['gcp'] = future
            
            # Wait for all to complete
            for provider, future in futures.items():
                try:
                    items = future.result(timeout=60)
                    all_items.extend(items)
                    logger.info("Ingested %d items from %s", len(items), provider)
                except Exception as e:
                    logger.error("Error ingesting %s billing data: %s", provider, str(e))
        
        logger.info("Total billing items ingested: %d", len(all_items))
        return all_items
    
    def process_billing_data(
        self,
        line_items: List[BillingLineItem],
        date: str
    ) -> List[CostEvent]:
        """
        Correlate billing line items to resources and create cost events.
        
        Args:
            line_items: Billing line items
            date: Date string (YYYY-MM-DD)
            
        Returns:
            List of CostEvent objects
        """
        logger.info("Processing %d billing line items", len(line_items))
        
        # Correlate
        correlated = self.correlator.correlate_line_items(line_items)
        
        # Create cost events
        events = self.correlator.create_cost_events(correlated, date)
        
        correlation_rate = sum(1 for _, rid, _ in correlated if rid) / len(correlated) if correlated else 0
        logger.info("Correlation rate: %.1f%%", correlation_rate * 100)
        
        return events
    
    def detect_anomalies(self, cost_events: List[CostEvent]) -> List[CostAnomaly]:
        """
        Detect anomalies in cost events.
        
        Args:
            cost_events: List of cost events
            
        Returns:
            List of CostAnomaly objects
        """
        logger.info("Detecting anomalies in %d cost events", len(cost_events))
        anomalies = self.anomaly_detector.detect_anomalies(cost_events)
        logger.info("Detected %d anomalies", len(anomalies))
        return anomalies
    
    def forecast_costs(
        self,
        cost_events: List[CostEvent],
        days: int = 30
    ) -> List[CostForecast]:
        """
        Forecast future costs.
        
        Args:
            cost_events: List of cost events
            days: Forecast period (7, 14, 30, 60, 90)
            
        Returns:
            List of CostForecast objects
        """
        logger.info("Generating %d-day forecasts for %d resources", days, len(cost_events))
        forecasts = self.forecaster.batch_forecast(cost_events, days)
        logger.info("Generated %d forecasts", len(forecasts))
        return forecasts
    
    def aggregate_by_team(self, cost_events: List[CostEvent]) -> List[CostByTeam]:
        """
        Aggregate costs by team.
        
        Args:
            cost_events: List of cost events
            
        Returns:
            List of CostByTeam objects
        """
        by_team: Dict[str, CostByTeam] = {}
        
        for event in cost_events:
            team_id = event.team_id or "unknown"
            
            if team_id not in by_team:
                by_team[team_id] = CostByTeam(
                    team_id=team_id,
                    total_daily_cost=0.0,
                    total_monthly_estimate=0.0
                )
            
            team_cost = by_team[team_id]
            team_cost.total_daily_cost += event.daily_cost
            team_cost.total_monthly_estimate += event.monthly_cost_estimate
            team_cost.resource_count += 1
            
            # Aggregate by service
            if event.service not in team_cost.cost_by_service:
                team_cost.cost_by_service[event.service] = 0.0
            team_cost.cost_by_service[event.service] += event.daily_cost
            
            # Aggregate by category
            category = event.cost_category.value
            if category not in team_cost.cost_by_category:
                team_cost.cost_by_category[category] = 0.0
            team_cost.cost_by_category[category] += event.daily_cost
        
        logger.info("Aggregated costs for %d teams", len(by_team))
        return list(by_team.values())
    
    async def run_pipeline(
        self,
        start_date: datetime,
        end_date: datetime,
        accounts: Optional[Dict[str, str]] = None,
        date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run complete cost intelligence pipeline.
        
        Args:
            start_date: Start of billing period
            end_date: End of billing period
            accounts: Dict of provider -> account_id
            date: Cost event date (defaults to today)
            
        Returns:
            Results dict with costs, anomalies, forecasts
        """
        date = date or datetime.utcnow().strftime('%Y-%m-%d')
        
        try:
            # Ingest
            line_items = self.ingest_billing_data(start_date, end_date, accounts)
            if not line_items:
                logger.warning("No billing items ingested")
                return {
                    'cost_events': [],
                    'anomalies': [],
                    'forecasts': [],
                    'by_team': []
                }
            
            # Process
            cost_events = self.process_billing_data(line_items, date)
            
            # Analyze
            anomalies = self.detect_anomalies(cost_events)
            forecasts = self.forecast_costs(cost_events, days=30)
            by_team = self.aggregate_by_team(cost_events)
            
            logger.info("Pipeline complete: %d events, %d anomalies, %d forecasts, %d teams",
                       len(cost_events), len(anomalies), len(forecasts), len(by_team))
            
            return {
                'cost_events': cost_events,
                'anomalies': anomalies,
                'forecasts': forecasts,
                'by_team': by_team
            }
            
        except Exception as e:
            logger.error("Pipeline failed: %s", str(e))
            raise
