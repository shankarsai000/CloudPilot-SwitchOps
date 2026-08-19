"""
Anomaly Detector - Spike detection and anomaly classification
30% threshold, <5% false positive rate
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from statistics import mean, stdev

from models_cost import CostEvent, CostAnomaly, CostCategory

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detects cost anomalies using statistical methods."""
    
    SPIKE_THRESHOLD = 0.30  # 30% increase threshold
    MIN_HISTORY = 7  # Minimum days for baseline
    SMOOTHING_FACTOR = 0.95  # For false positive reduction
    
    def __init__(self) -> None:
        """Initialize anomaly detector."""
        self.history: Dict[str, List[Tuple[str, float]]] = {}
        logger.info("Anomaly detector initialized (threshold=%.0f%%)", self.SPIKE_THRESHOLD * 100)
    
    def add_historical_data(
        self,
        resource_id: str,
        daily_costs: List[Tuple[str, float]]
    ) -> None:
        """
        Add historical cost data for baseline calculation.
        
        Args:
            resource_id: Resource identifier
            daily_costs: List of (date, cost) tuples
        """
        if resource_id not in self.history:
            self.history[resource_id] = []
        self.history[resource_id].extend(daily_costs)
        logger.debug("Added %d historical records for resource %s", len(daily_costs), resource_id)
    
    def detect_anomalies(
        self,
        cost_events: List[CostEvent]
    ) -> List[CostAnomaly]:
        """
        Detect anomalies in cost events.
        
        Args:
            cost_events: List of cost events
            
        Returns:
            List of detected anomalies
        """
        anomalies: List[CostAnomaly] = []
        
        # Group by resource
        by_resource: Dict[str, List[CostEvent]] = {}
        for event in cost_events:
            key = event.resource_id or event.service
            if key not in by_resource:
                by_resource[key] = []
            by_resource[key].append(event)
        
        # Detect anomalies per resource
        for resource_key, events in by_resource.items():
            baseline, stddev_val = self._calculate_baseline(resource_key)
            
            if baseline is None:
                logger.debug("Insufficient history for resource %s", resource_key)
                continue
            
            for event in events:
                anomaly = self._check_spike(event, baseline, stddev_val)
                if anomaly:
                    anomalies.append(anomaly)
                    logger.info("Detected anomaly: %s (%.0f%% spike)", anomaly.anomaly_id, anomaly.spike_percentage)
        
        logger.info("Detected %d anomalies in %d events", len(anomalies), len(cost_events))
        return anomalies
    
    def _calculate_baseline(self, resource_id: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate baseline cost and standard deviation.
        
        Args:
            resource_id: Resource identifier
            
        Returns:
            (baseline_cost, stddev) or (None, None) if insufficient data
        """
        if resource_id not in self.history:
            return None, None
        
        costs = [cost for _, cost in self.history[resource_id]]
        
        if len(costs) < self.MIN_HISTORY:
            return None, None
        
        # Use last 30 days for baseline
        recent_costs = costs[-30:] if len(costs) > 30 else costs
        
        baseline = mean(recent_costs)
        
        # Calculate standard deviation
        try:
            stddev_val = stdev(recent_costs) if len(recent_costs) > 1 else 0.0
        except ValueError:
            stddev_val = 0.0
        
        return baseline, stddev_val
    
    def _check_spike(
        self,
        event: CostEvent,
        baseline: float,
        stddev_val: float
    ) -> Optional[CostAnomaly]:
        """
        Check if event represents a spike.
        
        Args:
            event: Cost event
            baseline: Baseline daily cost
            stddev_val: Standard deviation
            
        Returns:
            CostAnomaly if spike detected, None otherwise
        """
        if baseline <= 0:
            return None
        
        # Calculate percentage increase
        increase_pct = (event.daily_cost - baseline) / baseline
        
        # Apply smoothing to reduce false positives
        # Only flag if spike is significant relative to variance
        if stddev_val > 0:
            z_score = increase_pct / (stddev_val / baseline) if baseline > 0 else 0
            threshold_z = 2.0  # ~95% confidence
            if z_score < threshold_z:
                return None
        
        # Check percentage threshold
        if increase_pct < self.SPIKE_THRESHOLD:
            return None
        
        # Spike detected
        severity = self._classify_severity(increase_pct)
        
        anomaly = CostAnomaly(
            anomaly_id=f"anom-{event.cost_event_id}",
            resource_id=event.resource_id,
            resource_name=event.resource_name,
            app_id=event.app_id,
            team_id=event.team_id,
            service=event.service,
            cost_category=event.cost_category,
            anomaly_type="spike",
            baseline_daily_cost=baseline,
            anomaly_daily_cost=event.daily_cost,
            spike_percentage=increase_pct * 100,
            severity=severity,
            start_date=event.date,
            root_cause_hypothesis=self._suggest_cause(event, increase_pct)
        )
        
        return anomaly
    
    def _classify_severity(self, increase_pct: float) -> str:
        """
        Classify anomaly severity.
        
        Args:
            increase_pct: Percentage increase
            
        Returns:
            Severity level (critical, warning, info)
        """
        if increase_pct >= 1.0:  # 100% increase
            return "critical"
        elif increase_pct >= 0.5:  # 50% increase
            return "warning"
        else:
            return "info"
    
    def _suggest_cause(self, event: CostEvent, increase_pct: float) -> str:
        """
        Suggest root cause for anomaly.
        
        Args:
            event: Cost event
            increase_pct: Percentage increase
            
        Returns:
            Root cause hypothesis
        """
        service = event.service.lower()
        
        if 'compute' in event.cost_category.value:
            if increase_pct > 1.0:
                return "Possible instance upscaling or unoptimized workload"
            else:
                return "Increased compute utilization"
        elif 'storage' in event.cost_category.value:
            return "Increased data storage or backups"
        elif 'network' in event.cost_category.value:
            return "Increased data transfer or bandwidth usage"
        elif 'database' in event.cost_category.value:
            return "Increased queries or database operations"
        else:
            return "Check service usage and configuration"
