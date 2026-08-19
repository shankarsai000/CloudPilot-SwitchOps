"""
GCP BigQuery Billing Export Adapter
Ingests GCP cost data from BigQuery billing export
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from models_cost import BillingLineItem, CostProvider, CostCategory

logger = logging.getLogger(__name__)


class GCPBillingAdapter:
    """GCP BigQuery billing export adapter for cost data ingestion."""
    
    def __init__(self, project_id: str, dataset_id: str = "billing_export") -> None:
        """
        Initialize GCP billing adapter.
        
        Args:
            project_id: GCP project ID
            dataset_id: BigQuery dataset ID for billing export
        """
        self.project_id = project_id
        self.dataset_id = dataset_id
        self._client: Optional[Any] = None
        logger.info("GCP billing adapter initialized (project=%s, dataset=%s)", 
                   project_id, dataset_id)
    
    @property
    def client(self) -> Any:
        """Lazy-load BigQuery client."""
        if self._client is None:
            try:
                # In production: from google.cloud import bigquery
                # self._client = bigquery.Client(project=self.project_id)
                logger.debug("BigQuery client initialized")
                self._client = {}
            except Exception as e:
                logger.error("Failed to create BigQuery client: %s", str(e))
                raise
        return self._client
    
    def get_billing_data(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[BillingLineItem]:
        """
        Fetch billing data from GCP BigQuery.
        
        Args:
            start_date: Start of billing period
            end_date: End of billing period
            
        Returns:
            List of BillingLineItem objects
        """
        items: List[BillingLineItem] = []
        
        try:
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            logger.info("Fetching GCP billing data (%s to %s)", start_str, end_str)
            
            results = self._query_billing_export(start_date, end_date)
            
            for result in results:
                item = self._parse_billing_record(result, start_date, end_date)
                if item:
                    items.append(item)
            
            logger.info("Fetched %d billing line items from GCP", len(items))
            
        except Exception as e:
            logger.error("Error fetching GCP billing data: %s", str(e))
            raise
        
        return items
    
    def _query_billing_export(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Query GCP BigQuery for billing data.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List of billing records
        """
        # In production:
        # query = f"""
        #   SELECT service.description, sku.description, location.region,
        #     resource.name, usage.amount_in_pricing_units, usage.pricing_unit,
        #     cost, usage_start_time, usage_end_time, labels
        #   FROM `{self.project_id}.{self.dataset_id}.gcp_billing_export_v1_*`
        #   WHERE _TABLE_SUFFIX BETWEEN '{start_date.strftime('%Y%m%d')}' 
        #     AND '{end_date.strftime('%Y%m%d')}'
        # """
        # results = self.client.query(query).result()
        
        return []
    
    def _parse_billing_record(
        self,
        record: Dict[str, Any],
        period_start: datetime,
        period_end: datetime
    ) -> Optional[BillingLineItem]:
        """
        Parse a GCP billing record.
        
        Args:
            record: Billing record from BigQuery
            period_start: Billing period start
            period_end: Billing period end
            
        Returns:
            BillingLineItem or None
        """
        try:
            service = record.get('service_description', 'Unknown')
            region = record.get('location_region', 'us-central1')
            resource_name = record.get('resource_name', '')
            cost = float(record.get('cost', 0))
            quantity = float(record.get('usage_amount', 1))
            unit = record.get('pricing_unit', 'hours')
            
            if cost <= 0:
                return None
            
            cost_category = self._map_service_to_category(service)
            
            # Extract labels/tags
            tags = {}
            labels = record.get('labels', [])
            if isinstance(labels, list):
                for label in labels:
                    tags[label.get('key', '')] = label.get('value', '')
            
            line_item = BillingLineItem(
                line_item_id=f"gcp-{self.project_id}-{service}-{region}-{int(period_start.timestamp())}",
                provider=CostProvider.GCP,
                account_id=self.project_id,
                service=service,
                resource_id=resource_name,
                resource_name=resource_name.split('/')[-1] if resource_name else None,
                region=region,
                cost_category=cost_category,
                usage_type=record.get('sku_description', service),
                usage_quantity=quantity,
                usage_unit=unit,
                cost_amount=cost,
                billing_period_start=period_start,
                billing_period_end=period_end,
                tags=tags
            )
            
            return line_item
            
        except (KeyError, ValueError) as e:
            logger.warning("Failed to parse GCP billing record: %s", str(e))
            return None
    
    @staticmethod
    def _map_service_to_category(service: str) -> CostCategory:
        """Map GCP service to cost category."""
        service_lower = service.lower()
        
        if any(x in service_lower for x in ['compute engine', 'gke', 'app engine', 'cloud run', 'cloud functions']):
            return CostCategory.COMPUTE
        elif any(x in service_lower for x in ['cloud storage', 'persistent disk']):
            return CostCategory.STORAGE
        elif any(x in service_lower for x in ['cloud cdn', 'cloud interconnect', 'cloud vpn']):
            return CostCategory.NETWORK
        elif any(x in service_lower for x in ['cloud sql', 'cloud spanner', 'cloud datastore', 'firestore']):
            return CostCategory.DATABASE
        else:
            return CostCategory.OTHER
