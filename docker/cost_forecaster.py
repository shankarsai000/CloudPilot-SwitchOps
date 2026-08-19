"""
Cost Forecaster - Simple trend forecasting
30/60/90-day trend forecasting using moving averages
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

from models_cost import CostEvent, CostForecast, CostCategory

logger = logging.getLogger(__name__)


class CostForecaster:
    """Forecasts future costs using moving averages."""
    
    def __init__(self) -> None:
        """Initialize cost forecaster."""
        self.history: Dict[str, List[Tuple[str, float]]] = {}
        logger.info("Cost forecaster initialized")
    
    def add_historical_data(
        self,
        resource_id: str,
        daily_costs: List[Tuple[str, float]]
    ) -> None:
        """
        Add historical cost data for forecasting.
        
        Args:
            resource_id: Resource identifier
            daily_costs: List of (date, cost) tuples
        """
        if resource_id not in self.history:
            self.history[resource_id] = []
        self.history[resource_id].extend(daily_costs)
        logger.debug("Added %d historical records for forecasting (resource=%s)", 
                    len(daily_costs), resource_id)
    
    def forecast(
        self,
        cost_event: CostEvent,
        days: int = 30
    ) -> Optional[CostForecast]:
        """
        Forecast future costs for a resource.
        
        Args:
            cost_event: Current cost event
            days: Number of days to forecast (7, 14, 30, 60, 90)
            
        Returns:
            CostForecast or None if insufficient data
        """
        if days not in [7, 14, 30, 60, 90]:
            logger.warning("Unsupported forecast period: %d days", days)
            return None
        
        resource_key = cost_event.resource_id or cost_event.service
        
        if resource_key not in self.history:
            return self._create_simple_forecast(cost_event, days)
        
        historical_costs = self.history[resource_key]
        
        if len(historical_costs) < days:
            return self._create_simple_forecast(cost_event, days)
        
        # Calculate moving average based on period
        moving_avg = self._calculate_moving_average(historical_costs, days)
        
        # Create forecast
        forecast_end = datetime.utcnow() + timedelta(days=days)
        monthly_estimate = moving_avg * 30
        
        forecast_type = f"{days}day_avg"
        
        forecast = CostForecast(
            forecast_id=f"fc-{cost_event.cost_event_id}-{days}d",
            resource_id=cost_event.resource_id,
            service=cost_event.service,
            cost_category=cost_event.cost_category,
            forecast_days=days,
            forecast_type=forecast_type,
            current_daily_cost=moving_avg,
            forecasted_monthly_cost=monthly_estimate,
            confidence_interval=self._calculate_confidence(historical_costs, days),
            forecast_end_date=forecast_end.strftime('%Y-%m-%d')
        )
        
        logger.info("Generated %d-day forecast: %.2f USD/day -> %.2f USD/month", 
                   days, moving_avg, monthly_estimate)
        
        return forecast
    
    def _calculate_moving_average(
        self,
        costs: List[Tuple[str, float]],
        window: int
    ) -> float:
        """
        Calculate moving average.
        
        Args:
            costs: List of (date, cost) tuples
            window: Window size for average
            
        Returns:
            Moving average value
        """
        # Use last 'window' days
        recent = costs[-window:] if len(costs) > window else costs
        cost_values = [cost for _, cost in recent]
        
        if not cost_values:
            return 0.0
        
        return sum(cost_values) / len(cost_values)
    
    def _calculate_confidence(
        self,
        costs: List[Tuple[str, float]],
        days: int
    ) -> float:
        """
        Calculate forecast confidence interval.
        
        Args:
            costs: Historical costs
            days: Forecast period
            
        Returns:
            Confidence level (0.0-1.0)
        """
        history_days = len(costs)
        
        # More historical data = higher confidence
        if history_days >= 90:
            base_confidence = 0.95
        elif history_days >= 30:
            base_confidence = 0.85
        elif history_days >= 14:
            base_confidence = 0.75
        elif history_days >= 7:
            base_confidence = 0.65
        else:
            base_confidence = 0.5
        
        # Longer forecast = lower confidence
        confidence_decay = 1.0 - (days / 120.0)
        
        return max(base_confidence * confidence_decay, 0.3)
    
    def _create_simple_forecast(
        self,
        cost_event: CostEvent,
        days: int
    ) -> CostForecast:
        """
        Create simple forecast using current day's cost.
        
        Args:
            cost_event: Current cost event
            days: Forecast period
            
        Returns:
            CostForecast with simple projection
        """
        forecast_end = datetime.utcnow() + timedelta(days=days)
        monthly_estimate = cost_event.daily_cost * 30
        
        forecast = CostForecast(
            forecast_id=f"fc-{cost_event.cost_event_id}-{days}d-simple",
            resource_id=cost_event.resource_id,
            service=cost_event.service,
            cost_category=cost_event.cost_category,
            forecast_days=days,
            forecast_type=f"{days}day_avg",
            current_daily_cost=cost_event.daily_cost,
            forecasted_monthly_cost=monthly_estimate,
            confidence_interval=0.5,  # Low confidence without history
            forecast_end_date=forecast_end.strftime('%Y-%m-%d')
        )
        
        return forecast
    
    def batch_forecast(
        self,
        cost_events: List[CostEvent],
        days: int = 30
    ) -> List[CostForecast]:
        """
        Generate forecasts for multiple cost events.
        
        Args:
            cost_events: List of cost events
            days: Forecast period
            
        Returns:
            List of CostForecast objects
        """
        forecasts: List[CostForecast] = []
        
        for event in cost_events:
            forecast = self.forecast(event, days)
            if forecast:
                forecasts.append(forecast)
        
        logger.info("Generated %d forecasts for %d events (%d-day period)", 
                   len(forecasts), len(cost_events), days)
        
        return forecasts
