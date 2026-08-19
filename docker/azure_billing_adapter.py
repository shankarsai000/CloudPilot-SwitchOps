"""
Azure Cost Management Billing Adapter
Ingests Azure cost data via Azure SDK
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from models_cost import BillingLineItem, CostProvider, CostCategory

logger = logging.getLogger(__name__)


class AzureBillingAdapter:
    """Azure Cost Management adapter for billing data ingestion."""
    
    def __init__(self, subscription_id: str, tenant_id: Optional[str] = None) -> None:
        """
        Initialize Azure billing adapter.
        
        Args:
            subscription_id: Azure subscription ID
            tenant_id: Azure tenant ID (optional, for multi-tenant scenarios)
        """
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id
        self._client: Optional[Any] = None
        logger.info("Azure billing adapter initialized (subscription=%s)", subscription_id)
    
    @property
    def client(self) -> Any:
        """Lazy-load Azure Cost Management client."""
        if self._client is None:
            try:
                # In production, use: from azure.mgmt.costmanagement import CostManagementClient
                # For now, simulate the client
                logger.debug("Azure Cost Management client initialized")
                self._client = {}
            except Exception as e:
                logger.error("Failed to create Azure client: %s", str(e))
                raise
        return self._client
    
    def get_billing_data(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[BillingLineItem]:
        """
        Fetch billing data from Azure Cost Management.
        
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
            
            logger.info("Fetching Azure billing data (%s to %s)", start_str, end_str)
            
            # Simulate API call with mock data structure
            results = self._query_cost_data(start_date, end_date)
            
            for result in results:
                item = self._parse_usage_record(result, start_date, end_date)
                if item:
                    items.append(item)
            
            logger.info("Fetched %d billing line items from Azure", len(items))
            
        except Exception as e:
            logger.error("Error fetching Azure billing data: %s", str(e))
            raise
        
        return items
    
    def _query_cost_data(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Query Azure Cost Management API.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List of cost records
        """
        # In production, this would call Azure Cost Management API
        # For now, return empty list (tests will mock this)
        return []
    
    def _parse_usage_record(
        self,
        record: Dict[str, Any],
        period_start: datetime,
        period_end: datetime
    ) -> Optional[BillingLineItem]:
        """
        Parse an Azure usage record.
        
        Args:
            record: Usage record from Azure API
            period_start: Billing period start
            period_end: Billing period end
            
        Returns:
            BillingLineItem or None
        """
        try:
            service = record.get('MeterCategory', 'Unknown')
            resource_id = record.get('ResourceId', '')
            region = record.get('ResourceLocation', 'eastus')
            cost = float(record.get('PreTaxCost', 0))
            quantity = float(record.get('Quantity', 1))
            
            if cost <= 0:
                return None
            
            resource_name = resource_id.split('/')[-1] if resource_id else None
            cost_category = self._map_service_to_category(service)
            
            line_item = BillingLineItem(
                line_item_id=f"azure-{self.subscription_id}-{service}-{region}-{int(period_start.timestamp())}",
                provider=CostProvider.AZURE,
                account_id=self.subscription_id,
                service=service,
                resource_id=resource_id,
                resource_name=resource_name,
                region=region,
                cost_category=cost_category,
                usage_type=record.get('MeterSubCategory', service),
                usage_quantity=quantity,
                usage_unit=record.get('Unit', 'hours'),
                cost_amount=cost,
                billing_period_start=period_start,
                billing_period_end=period_end,
                tags={"SubscriptionId": self.subscription_id}
            )
            
            return line_item
            
        except (KeyError, ValueError) as e:
            logger.warning("Failed to parse Azure usage record: %s", str(e))
            return None
    
    @staticmethod
    def _map_service_to_category(service: str) -> CostCategory:
        """Map Azure service to cost category."""
        service_lower = service.lower()
        
        if any(x in service_lower for x in ['virtual machines', 'app service', 'container instances', 'function']):
            return CostCategory.COMPUTE
        elif any(x in service_lower for x in ['storage', 'data lake', 'blob']):
            return CostCategory.STORAGE
        elif any(x in service_lower for x in ['bandwidth', 'traffic', 'cdn', 'expressroute']):
            return CostCategory.NETWORK
        elif any(x in service_lower for x in ['sql', 'cosmos', 'postgresql', 'mysql']):
            return CostCategory.DATABASE
        else:
            return CostCategory.OTHER
