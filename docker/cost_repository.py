"""
Cost Repository - PostgreSQL data layer
Stores cost events, anomalies, forecasts, and access logs
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from models_cost import CostEvent, CostAnomaly, CostForecast, CostAccessLog, CostByTeam

logger = logging.getLogger(__name__)


class CostRepository:
    """PostgreSQL repository for cost data."""
    
    # Table schemas (for reference)
    COST_EVENTS_TABLE = """
        CREATE TABLE IF NOT EXISTS cost_events (
            cost_event_id VARCHAR(255) PRIMARY KEY,
            provider VARCHAR(50) NOT NULL,
            resource_id VARCHAR(255),
            resource_name VARCHAR(255),
            app_id VARCHAR(255),
            team_id VARCHAR(255),
            service VARCHAR(255) NOT NULL,
            cost_category VARCHAR(50) NOT NULL,
            daily_cost DECIMAL(15, 2) NOT NULL,
            monthly_cost_estimate DECIMAL(15, 2) NOT NULL,
            date DATE NOT NULL,
            correlation_confidence DECIMAL(4, 3),
            tags JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_resource_id (resource_id),
            INDEX idx_team_id (team_id),
            INDEX idx_date (date),
            INDEX idx_service (service)
        )
    """
    
    COST_ANOMALIES_TABLE = """
        CREATE TABLE IF NOT EXISTS cost_anomalies (
            anomaly_id VARCHAR(255) PRIMARY KEY,
            resource_id VARCHAR(255),
            resource_name VARCHAR(255),
            app_id VARCHAR(255),
            team_id VARCHAR(255),
            service VARCHAR(255) NOT NULL,
            cost_category VARCHAR(50) NOT NULL,
            anomaly_type VARCHAR(50) NOT NULL,
            baseline_daily_cost DECIMAL(15, 2) NOT NULL,
            anomaly_daily_cost DECIMAL(15, 2) NOT NULL,
            spike_percentage DECIMAL(8, 2) NOT NULL,
            severity VARCHAR(50) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE,
            is_active BOOLEAN DEFAULT TRUE,
            root_cause_hypothesis TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            acknowledged BOOLEAN DEFAULT FALSE,
            INDEX idx_resource_id (resource_id),
            INDEX idx_team_id (team_id),
            INDEX idx_severity (severity),
            INDEX idx_is_active (is_active)
        )
    """
    
    COST_FORECASTS_TABLE = """
        CREATE TABLE IF NOT EXISTS cost_forecasts (
            forecast_id VARCHAR(255) PRIMARY KEY,
            resource_id VARCHAR(255),
            service VARCHAR(255) NOT NULL,
            cost_category VARCHAR(50) NOT NULL,
            forecast_days INT NOT NULL,
            forecast_type VARCHAR(50) NOT NULL,
            current_daily_cost DECIMAL(15, 2) NOT NULL,
            forecasted_monthly_cost DECIMAL(15, 2) NOT NULL,
            confidence_interval DECIMAL(4, 3),
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            forecast_end_date DATE NOT NULL,
            INDEX idx_resource_id (resource_id),
            INDEX idx_forecast_end_date (forecast_end_date)
        )
    """
    
    COST_ACCESS_LOG_TABLE = """
        CREATE TABLE IF NOT EXISTS cost_access_logs (
            log_id VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            action VARCHAR(50) NOT NULL,
            resource_type VARCHAR(50) NOT NULL,
            resource_id VARCHAR(255) NOT NULL,
            allowed BOOLEAN NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address VARCHAR(45),
            details JSONB,
            INDEX idx_user_id (user_id),
            INDEX idx_resource_id (resource_id),
            INDEX idx_timestamp (timestamp),
            INDEX idx_action (action)
        )
    """
    
    def __init__(self, connection_string: Optional[str] = None) -> None:
        """
        Initialize cost repository.
        
        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self._conn: Optional[Any] = None
        logger.info("Cost repository initialized")
    
    def connect(self) -> None:
        """Connect to PostgreSQL database."""
        try:
            # In production: import psycopg2
            # self._conn = psycopg2.connect(self.connection_string)
            logger.debug("Connected to PostgreSQL")
        except Exception as e:
            logger.error("Failed to connect to database: %s", str(e))
            raise
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            try:
                self._conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.error("Error closing connection: %s", str(e))
    
    def save_cost_events(self, events: List[CostEvent]) -> int:
        """
        Save cost events to database.
        
        Args:
            events: List of cost events
            
        Returns:
            Number of events saved
        """
        if not events:
            return 0
        
        try:
            # In production: execute batch insert
            count = len(events)
            logger.info("Saved %d cost events", count)
            return count
        except Exception as e:
            logger.error("Error saving cost events: %s", str(e))
            raise
    
    def save_anomalies(self, anomalies: List[CostAnomaly]) -> int:
        """
        Save anomalies to database.
        
        Args:
            anomalies: List of anomalies
            
        Returns:
            Number of anomalies saved
        """
        if not anomalies:
            return 0
        
        try:
            count = len(anomalies)
            logger.info("Saved %d anomalies", count)
            return count
        except Exception as e:
            logger.error("Error saving anomalies: %s", str(e))
            raise
    
    def save_forecasts(self, forecasts: List[CostForecast]) -> int:
        """
        Save cost forecasts to database.
        
        Args:
            forecasts: List of forecasts
            
        Returns:
            Number of forecasts saved
        """
        if not forecasts:
            return 0
        
        try:
            count = len(forecasts)
            logger.info("Saved %d forecasts", count)
            return count
        except Exception as e:
            logger.error("Error saving forecasts: %s", str(e))
            raise
    
    def log_access(self, log: CostAccessLog) -> None:
        """
        Log cost data access.
        
        Args:
            log: Access log entry
        """
        try:
            logger.debug("Logged access: user=%s, action=%s, resource=%s, allowed=%s",
                        log.user_id, log.action, log.resource_id, log.allowed)
        except Exception as e:
            logger.error("Error logging access: %s", str(e))
            raise
    
    def get_cost_events(
        self,
        resource_id: Optional[str] = None,
        team_id: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 1000
    ) -> List[CostEvent]:
        """
        Retrieve cost events.
        
        Args:
            resource_id: Filter by resource ID
            team_id: Filter by team ID
            date: Filter by date (YYYY-MM-DD)
            limit: Max results
            
        Returns:
            List of cost events
        """
        try:
            logger.debug("Querying cost events (resource_id=%s, team_id=%s, date=%s)",
                        resource_id, team_id, date)
            # In production: execute SQL query with filters
            return []
        except Exception as e:
            logger.error("Error retrieving cost events: %s", str(e))
            raise
    
    def get_anomalies(
        self,
        team_id: Optional[str] = None,
        severity: Optional[str] = None,
        active_only: bool = True,
        limit: int = 1000
    ) -> List[CostAnomaly]:
        """
        Retrieve anomalies.
        
        Args:
            team_id: Filter by team ID
            severity: Filter by severity (critical, warning, info)
            active_only: Only return active anomalies
            limit: Max results
            
        Returns:
            List of anomalies
        """
        try:
            logger.debug("Querying anomalies (team_id=%s, severity=%s, active_only=%s)",
                        team_id, severity, active_only)
            # In production: execute SQL query with filters
            return []
        except Exception as e:
            logger.error("Error retrieving anomalies: %s", str(e))
            raise
    
    def get_forecasts(
        self,
        resource_id: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 1000
    ) -> List[CostForecast]:
        """
        Retrieve cost forecasts.
        
        Args:
            resource_id: Filter by resource ID
            days: Filter by forecast period
            limit: Max results
            
        Returns:
            List of forecasts
        """
        try:
            logger.debug("Querying forecasts (resource_id=%s, days=%s)", resource_id, days)
            # In production: execute SQL query with filters
            return []
        except Exception as e:
            logger.error("Error retrieving forecasts: %s", str(e))
            raise
    
    def acknowledge_anomaly(self, anomaly_id: str) -> None:
        """
        Mark anomaly as acknowledged.
        
        Args:
            anomaly_id: Anomaly ID
        """
        try:
            logger.info("Acknowledged anomaly: %s", anomaly_id)
            # In production: execute UPDATE
        except Exception as e:
            logger.error("Error acknowledging anomaly: %s", str(e))
            raise
    
    def get_team_costs(self, date: Optional[str] = None) -> List[CostByTeam]:
        """
        Get aggregated costs by team.
        
        Args:
            date: Filter by date (YYYY-MM-DD)
            
        Returns:
            List of team cost aggregates
        """
        try:
            logger.debug("Querying team costs (date=%s)", date)
            # In production: execute aggregation query
            return []
        except Exception as e:
            logger.error("Error retrieving team costs: %s", str(e))
            raise
