"""
Cost Correlator - Match billing line items to M1 resources
Tag-based, naming convention, and rule-based correlation
"""

import logging
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher

from models_cost import BillingLineItem, CostEvent, CostProvider

logger = logging.getLogger(__name__)


class CostCorrelator:
    """Correlates billing line items to infrastructure resources from M1."""
    
    def __init__(self, resources: Optional[Dict[str, Dict]] = None) -> None:
        """
        Initialize cost correlator.
        
        Args:
            resources: Dict of resource_id -> resource metadata from M1
        """
        self.resources = resources or {}
        logger.info("Cost correlator initialized with %d resources", len(self.resources))
    
    def update_resources(self, resources: Dict[str, Dict]) -> None:
        """Update resource metadata."""
        self.resources = resources
        logger.debug("Updated correlator with %d resources", len(resources))
    
    def correlate_line_items(
        self,
        line_items: List[BillingLineItem]
    ) -> List[Tuple[BillingLineItem, Optional[str], float]]:
        """
        Correlate billing line items to resources.
        
        Args:
            line_items: List of billing line items
            
        Returns:
            List of (line_item, resource_id, confidence) tuples
        """
        results: List[Tuple[BillingLineItem, Optional[str], float]] = []
        
        for item in line_items:
            resource_id, confidence = self._find_best_match(item)
            results.append((item, resource_id, confidence))
            
            if resource_id:
                logger.debug(
                    "Correlated %s (%s) to resource %s (confidence=%.2f)",
                    item.service, item.resource_name, resource_id, confidence
                )
        
        logger.info("Correlated %d/%d line items", 
                   sum(1 for _, rid, _ in results if rid), len(results))
        
        return results
    
    def _find_best_match(
        self,
        item: BillingLineItem
    ) -> Tuple[Optional[str], float]:
        """
        Find best matching resource for a billing line item.
        
        Args:
            item: Billing line item
            
        Returns:
            (resource_id, confidence_score)
        """
        candidates: List[Tuple[str, float]] = []
        
        # Strategy 1: Exact tag match
        if item.tags:
            for resource_id, resource in self.resources.items():
                score = self._match_by_tags(item.tags, resource.get('tags', {}))
                if score > 0:
                    candidates.append((resource_id, score))
        
        # Strategy 2: Resource ID or name match
        if item.resource_id:
            for resource_id, resource in self.resources.items():
                if item.resource_id == resource_id or item.resource_id == resource.get('name'):
                    candidates.append((resource_id, 0.95))
        
        # Strategy 3: Naming convention match
        if item.resource_name:
            for resource_id, resource in self.resources.items():
                score = self._match_by_name(
                    item.resource_name,
                    resource.get('name', ''),
                    item.service
                )
                if score > 0.7:
                    candidates.append((resource_id, score))
        
        # Strategy 4: Service/region/account match (fallback)
        for resource_id, resource in self.resources.items():
            if (resource.get('provider') == item.provider.value and
                resource.get('region') == item.region):
                score = self._match_by_service_compatibility(item.service, resource)
                if score > 0.5:
                    candidates.append((resource_id, score))
        
        if not candidates:
            return None, 0.0
        
        # Return best match
        best_id, best_score = max(candidates, key=lambda x: x[1])
        
        # Normalize score to 0.0-1.0 range
        normalized_score = min(best_score, 1.0)
        
        return best_id if normalized_score > 0.3 else None, normalized_score
    
    def _match_by_tags(self, item_tags: Dict[str, str], resource_tags: Dict[str, str]) -> float:
        """
        Match billing item to resource by tags.
        
        Args:
            item_tags: Tags from billing item
            resource_tags: Tags from resource
            
        Returns:
            Match score (0.0-1.0)
        """
        if not resource_tags:
            return 0.0
        
        matches = 0
        for key, value in item_tags.items():
            if resource_tags.get(key) == value:
                matches += 1
        
        return min(matches / max(len(resource_tags), 1), 1.0) * 0.9
    
    def _match_by_name(self, item_name: str, resource_name: str, service: str) -> float:
        """
        Match billing item to resource by name similarity.
        
        Args:
            item_name: Resource name from billing item
            resource_name: Resource name from M1
            service: Service name
            
        Returns:
            Match score (0.0-1.0)
        """
        if not item_name or not resource_name:
            return 0.0
        
        item_norm = item_name.lower().replace('-', '').replace('_', '')
        resource_norm = resource_name.lower().replace('-', '').replace('_', '')
        
        # Exact match
        if item_norm == resource_norm:
            return 1.0
        
        # Substring match
        if item_norm in resource_norm or resource_norm in item_norm:
            return 0.85
        
        # Sequence similarity
        ratio = SequenceMatcher(None, item_norm, resource_norm).ratio()
        if ratio > 0.8:
            return ratio
        
        return 0.0
    
    def _match_by_service_compatibility(self, service: str, resource: Dict) -> float:
        """
        Match billing item to resource by service type compatibility.
        
        Args:
            service: Service from billing item
            resource: Resource metadata
            
        Returns:
            Match score (0.0-1.0)
        """
        resource_type = resource.get('type', '').lower()
        service_lower = service.lower()
        
        # Service compatibility mapping
        compatibility_map = {
            'ec2': ['instance', 'vm', 'server'],
            'rds': ['database', 'db', 'sql'],
            's3': ['storage', 'bucket'],
            'lambda': ['function', 'serverless'],
            'elb': ['load-balancer', 'nlb', 'alb'],
            'virtualnetwork': ['network', 'vpc', 'vnet'],
        }
        
        for svc, compatible_types in compatibility_map.items():
            if svc in service_lower:
                for ctype in compatible_types:
                    if ctype in resource_type:
                        return 0.75
        
        return 0.4
    
    def create_cost_events(
        self,
        correlated_items: List[Tuple[BillingLineItem, Optional[str], float]],
        date: str
    ) -> List[CostEvent]:
        """
        Create cost events from correlated items.
        
        Args:
            correlated_items: List of (item, resource_id, confidence) tuples
            date: Date string (YYYY-MM-DD)
            
        Returns:
            List of CostEvent objects
        """
        events: List[CostEvent] = []
        
        for item, resource_id, confidence in correlated_items:
            event = CostEvent(
                cost_event_id=item.line_item_id,
                provider=item.provider,
                resource_id=resource_id,
                resource_name=item.resource_name,
                service=item.service,
                cost_category=item.cost_category,
                daily_cost=item.cost_amount,
                monthly_cost_estimate=item.cost_amount * 30,
                date=date,
                correlation_confidence=confidence,
                tags=item.tags
            )
            events.append(event)
        
        return events
