"""
Cost Intelligence Agent - Pydantic Models
Cost events, billing line items, anomalies, forecasts
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator


class CostProvider(str, Enum):
    """Cloud provider enum."""
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class CostCategory(str, Enum):
    """Cost category enum."""
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    DATABASE = "database"
    OTHER = "other"


class BillingLineItem(BaseModel):
    """Individual billing line item from cloud provider."""
    
    line_item_id: str = Field(..., description="Unique line item ID from provider")
    provider: CostProvider = Field(..., description="Cloud provider")
    account_id: str = Field(..., description="Provider account ID")
    service: str = Field(..., description="Service name (e.g., EC2, VirtualMachine)")
    resource_id: Optional[str] = Field(None, description="Cloud resource ID")
    resource_name: Optional[str] = Field(None, description="Human-readable resource name")
    region: Optional[str] = Field(None, description="Provider region")
    cost_category: CostCategory = Field(..., description="Cost category")
    usage_type: str = Field(..., description="Usage type (e.g., compute-hours, gb-month)")
    usage_quantity: float = Field(..., ge=0, description="Quantity used")
    usage_unit: str = Field(..., description="Unit of measurement")
    cost_amount: float = Field(..., ge=0, description="Cost in USD")
    currency: str = Field(default="USD", description="Currency code")
    billing_period_start: datetime = Field(..., description="Billing period start")
    billing_period_end: datetime = Field(..., description="Billing period end")
    tags: Dict[str, str] = Field(default_factory=dict, description="Resource tags")
    
    class Config:
        json_schema_extra = {
            "example": {
                "line_item_id": "aws-item-12345",
                "provider": "aws",
                "account_id": "123456789012",
                "service": "EC2",
                "resource_id": "i-0123456789abcdef0",
                "resource_name": "web-server-01",
                "region": "us-east-1",
                "cost_category": "compute",
                "usage_type": "compute-hours",
                "usage_quantity": 730.0,
                "usage_unit": "hours",
                "cost_amount": 145.60,
                "billing_period_start": "2024-01-01T00:00:00Z",
                "billing_period_end": "2024-01-31T23:59:59Z",
                "tags": {"env": "prod", "app": "web"}
            }
        }


class CostEvent(BaseModel):
    """Cost event aggregated from billing line items."""
    
    cost_event_id: str = Field(..., description="Unique cost event ID")
    provider: CostProvider = Field(..., description="Cloud provider")
    resource_id: Optional[str] = Field(None, description="Correlated M1 resource ID")
    resource_name: Optional[str] = Field(None, description="Correlated resource name")
    app_id: Optional[str] = Field(None, description="Application ID (from M1)")
    team_id: Optional[str] = Field(None, description="Team ID")
    service: str = Field(..., description="Service name")
    cost_category: CostCategory = Field(..., description="Cost category")
    daily_cost: float = Field(..., ge=0, description="Daily cost in USD")
    monthly_cost_estimate: float = Field(..., ge=0, description="Estimated monthly cost")
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    correlation_confidence: float = Field(default=0.0, ge=0.0, le=1.0, 
                                         description="Confidence of resource correlation")
    tags: Dict[str, str] = Field(default_factory=dict, description="Tags")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('date')
    def validate_date(cls, v: str) -> str:
        """Validate date format."""
        try:
            datetime.strptime(v, '%Y-%m-%d')
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class CostAnomaly(BaseModel):
    """Detected cost anomaly."""
    
    anomaly_id: str = Field(..., description="Unique anomaly ID")
    resource_id: Optional[str] = Field(None, description="Resource ID")
    resource_name: Optional[str] = Field(None, description="Resource name")
    app_id: Optional[str] = Field(None, description="Application ID")
    team_id: Optional[str] = Field(None, description="Team ID")
    service: str = Field(..., description="Service name")
    cost_category: CostCategory = Field(..., description="Cost category")
    anomaly_type: str = Field(..., description="Type (spike, sustained_increase, etc.)")
    baseline_daily_cost: float = Field(..., ge=0, description="Baseline daily cost")
    anomaly_daily_cost: float = Field(..., ge=0, description="Current daily cost")
    spike_percentage: float = Field(..., description="% increase from baseline")
    severity: str = Field(..., description="critical, warning, info")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    is_active: bool = Field(default=True, description="Anomaly still active")
    root_cause_hypothesis: Optional[str] = Field(None, description="Possible cause")
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = Field(default=False, description="Team acknowledged anomaly")
    
    class Config:
        json_schema_extra = {
            "example": {
                "anomaly_id": "anom-001",
                "resource_id": "i-0123456789abcdef0",
                "service": "EC2",
                "cost_category": "compute",
                "anomaly_type": "spike",
                "baseline_daily_cost": 10.0,
                "anomaly_daily_cost": 13.2,
                "spike_percentage": 32.0,
                "severity": "warning",
                "start_date": "2024-01-15",
                "root_cause_hypothesis": "Increased instance size or unoptimized workload"
            }
        }


class CostForecast(BaseModel):
    """Cost forecast for specified period."""
    
    forecast_id: str = Field(..., description="Unique forecast ID")
    resource_id: Optional[str] = Field(None, description="Resource ID")
    service: str = Field(..., description="Service name")
    cost_category: CostCategory = Field(..., description="Cost category")
    forecast_days: int = Field(..., ge=1, le=90, description="Days to forecast (1-90)")
    forecast_type: str = Field(..., description="Type (7day_avg, 14day_avg, 30day_avg)")
    current_daily_cost: float = Field(..., ge=0, description="Current daily cost average")
    forecasted_monthly_cost: float = Field(..., ge=0, description="Forecasted monthly cost")
    confidence_interval: float = Field(default=0.85, ge=0.0, le=1.0, 
                                       description="Confidence level")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    forecast_end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "forecast_id": "fc-001",
                "resource_id": "i-0123456789abcdef0",
                "service": "EC2",
                "cost_category": "compute",
                "forecast_days": 30,
                "forecast_type": "30day_avg",
                "current_daily_cost": 10.5,
                "forecasted_monthly_cost": 315.0,
                "confidence_interval": 0.85
            }
        }


class CostByTeam(BaseModel):
    """Cost aggregated by team."""
    
    team_id: str = Field(..., description="Team ID")
    team_name: Optional[str] = Field(None, description="Team name")
    total_daily_cost: float = Field(..., ge=0, description="Total daily cost")
    total_monthly_estimate: float = Field(..., ge=0, description="Monthly estimate")
    cost_by_service: Dict[str, float] = Field(default_factory=dict, 
                                              description="Cost breakdown by service")
    cost_by_category: Dict[str, float] = Field(default_factory=dict,
                                               description="Cost breakdown by category")
    resource_count: int = Field(default=0, description="Number of resources")
    
    class Config:
        json_schema_extra = {
            "example": {
                "team_id": "team-001",
                "team_name": "Platform",
                "total_daily_cost": 150.0,
                "total_monthly_estimate": 4500.0,
                "cost_by_service": {"EC2": 100.0, "S3": 50.0},
                "cost_by_category": {"compute": 100.0, "storage": 50.0},
                "resource_count": 5
            }
        }


class CostAccessLog(BaseModel):
    """Audit log for cost data access."""
    
    log_id: str = Field(..., description="Unique log ID")
    user_id: str = Field(..., description="User ID")
    action: str = Field(..., description="Action (view_costs, export, view_anomalies, etc.)")
    resource_type: str = Field(..., description="Resource type (team, service, resource)")
    resource_id: str = Field(..., description="Resource ID")
    allowed: bool = Field(..., description="Access allowed or denied")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = Field(None, description="User IP address")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "log_id": "log-001",
                "user_id": "user-123",
                "action": "view_costs",
                "resource_type": "team",
                "resource_id": "team-001",
                "allowed": True,
                "timestamp": "2024-01-15T10:30:00Z",
                "ip_address": "192.168.1.1"
            }
        }
