"""
AWS Cost Explorer Billing Adapter
Ingests AWS cost data via boto3 Cost Explorer API
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

from models_cost import BillingLineItem, CostProvider, CostCategory

logger = logging.getLogger(__name__)


class AWSBillingAdapter:
    """AWS Cost Explorer adapter for billing data ingestion."""
    
    def __init__(self, region: str = "us-east-1", profile_name: Optional[str] = None) -> None:
        """
        Initialize AWS billing adapter.
        
        Args:
            region: AWS region
            profile_name: AWS profile name for credentials
        """
        self.region = region
        self.profile_name = profile_name
        self._client: Optional[Any] = None
        logger.info("AWS billing adapter initialized (region=%s)", region)
    
    @property
    def client(self) -> Any:
        """Lazy-load boto3 Cost Explorer client."""
        if self._client is None:
            try:
                if self.profile_name:
                    session = boto3.Session(profile_name=self.profile_name)
                    self._client = session.client('ce', region_name=self.region)
                else:
                    self._client = boto3.client('ce', region_name=self.region)
                logger.debug("Cost Explorer client created")
            except ClientError as e:
                logger.error("Failed to create Cost Explorer client: %s", str(e))
                raise
        return self._client
    
    def get_billing_data(
        self,
        start_date: datetime,
        end_date: datetime,
        account_id: str
    ) -> List[BillingLineItem]:
        """
        Fetch billing data from AWS Cost Explorer.
        
        Args:
            start_date: Start of billing period
            end_date: End of billing period
            account_id: AWS account ID
            
        Returns:
            List of BillingLineItem objects
        """
        items: List[BillingLineItem] = []
        
        try:
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            logger.info("Fetching AWS billing data (%s to %s)", start_str, end_str)
            
            response = self.client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_str,
                    'End': end_str
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                GroupBy=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'REGION'},
                    {'Type': 'DIMENSION', 'Key': 'RESOURCE_ID'},
                    {'Type': 'TAG', 'Key': 'Environment'}
                ],
                Filter={
                    'Dimensions': {
                        'Key': 'LINKED_ACCOUNT',
                        'Values': [account_id]
                    }
                }
            )
            
            for result in response.get('ResultsByTime', []):
                period_start = datetime.strptime(result['TimePeriod']['Start'], '%Y-%m-%d')
                period_end = datetime.strptime(result['TimePeriod']['End'], '%Y-%m-%d')
                
                for group in result.get('Groups', []):
                    item = self._parse_cost_group(
                        group=group,
                        account_id=account_id,
                        period_start=period_start,
                        period_end=period_end
                    )
                    if item:
                        items.append(item)
            
            logger.info("Fetched %d billing line items from AWS", len(items))
            
        except ClientError as e:
            logger.error("Cost Explorer API error: %s", str(e))
            raise
        except Exception as e:
            logger.error("Error fetching AWS billing data: %s", str(e))
            raise
        
        return items
    
    def _parse_cost_group(
        self,
        group: Dict[str, Any],
        account_id: str,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[BillingLineItem]:
        """
        Parse a cost group from AWS response.
        
        Args:
            group: Cost group from AWS API
            account_id: AWS account ID
            period_start: Billing period start
            period_end: Billing period end
            
        Returns:
            BillingLineItem or None
        """
        try:
            keys = group.get('Keys', [])
            metrics = group.get('Metrics', {})
            cost = float(metrics.get('UnblendedCost', {}).get('amount', 0))
            
            if cost <= 0:
                return None
            
            service = keys[0] if len(keys) > 0 else "Unknown"
            region = keys[1] if len(keys) > 1 else "us-east-1"
            resource_id = keys[2] if len(keys) > 2 else None
            env_tag = keys[3] if len(keys) > 3 else "unknown"
            
            cost_category = self._map_service_to_category(service)
            
            line_item = BillingLineItem(
                line_item_id=f"aws-{account_id}-{service}-{region}-{int(period_start.timestamp())}",
                provider=CostProvider.AWS,
                account_id=account_id,
                service=service,
                resource_id=resource_id,
                resource_name=resource_id.split('/')[-1] if resource_id else None,
                region=region,
                cost_category=cost_category,
                usage_type=service.lower(),
                usage_quantity=1.0,
                usage_unit="day",
                cost_amount=cost,
                billing_period_start=period_start,
                billing_period_end=period_end,
                tags={"Environment": env_tag}
            )
            
            return line_item
            
        except (KeyError, ValueError, IndexError) as e:
            logger.warning("Failed to parse cost group: %s", str(e))
            return None
    
    @staticmethod
    def _map_service_to_category(service: str) -> CostCategory:
        """Map AWS service to cost category."""
        service_lower = service.lower()
        
        if any(x in service_lower for x in ['ec2', 'rds', 'lambda', 'ecs', 'eks']):
            return CostCategory.COMPUTE
        elif any(x in service_lower for x in ['s3', 'ebs', 'glacier', 'backup']):
            return CostCategory.STORAGE
        elif any(x in service_lower for x in ['cloudfront', 'elb', 'nat', 'vpn']):
            return CostCategory.NETWORK
        elif any(x in service_lower for x in ['dynamodb', 'rds', 'redshift', 'elasticache']):
            return CostCategory.DATABASE
        else:
            return CostCategory.OTHER
