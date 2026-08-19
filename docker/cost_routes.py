"""
Cost Intelligence API Routes
FastAPI endpoints for cost data, anomalies, forecasts, by-team aggregation, access logs
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Header, Request

from models_cost import (
    CostEvent, CostAnomaly, CostForecast, CostByTeam, CostAccessLog,
    CostProvider
)
from cost_agent import CostIntelligenceAgent
from cost_repository import CostRepository
from cost_access_control import CostAccessControl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/costs", tags=["costs"])

# Initialize components
agent: Optional[CostIntelligenceAgent] = None
repository: Optional[CostRepository] = None
access_control: Optional[CostAccessControl] = None


def init_routes(
    cost_agent: CostIntelligenceAgent,
    cost_repo: CostRepository,
    access_ctrl: CostAccessControl
) -> APIRouter:
    """
    Initialize cost routes with components.
    
    Args:
        cost_agent: Cost Intelligence Agent
        cost_repo: Cost repository
        access_ctrl: Access control
        
    Returns:
        Configured APIRouter
    """
    global agent, repository, access_control
    agent = cost_agent
    repository = cost_repo
    access_control = access_ctrl
    return router


def _get_user_from_header(
    request: Request,
    authorization: Optional[str] = None
) -> tuple[str, str]:
    """
    Extract user ID and role from request header.
    
    Args:
        request: FastAPI request
        authorization: Authorization header
        
    Returns:
        (user_id, user_role)
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    # In production: verify JWT token
    # For now: parse "Bearer user_id:role"
    try:
        if authorization.startswith("Bearer "):
            auth_data = authorization[7:].split(":")
            if len(auth_data) == 2:
                return auth_data[0], auth_data[1]
    except Exception:
        pass
    
    raise HTTPException(status_code=401, detail="Invalid authorization format")


@router.get("", response_model=List[CostEvent])
async def get_costs(
    request: Request,
    authorization: Optional[str] = Header(None),
    resource_id: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=10000)
) -> List[CostEvent]:
    """
    Get cost events.
    
    Args:
        request: FastAPI request
        authorization: Authorization header (Bearer user_id:role)
        resource_id: Filter by resource ID
        team_id: Filter by team ID
        date: Filter by date (YYYY-MM-DD)
        limit: Max results
        
    Returns:
        List of cost events
    """
    try:
        user_id, user_role = _get_user_from_header(request, authorization)
        ip_address = request.client.host if request.client else None
        
        # Authorization check
        if not access_control.can_view_cost(
            user_id, user_role, "resource", resource_id or "all", team_id, ip_address
        ):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # In production: query from repository
        # return repository.get_cost_events(resource_id, team_id, date, limit)
        
        logger.info("Retrieved costs: user=%s, resource=%s, team=%s, date=%s", 
                   user_id, resource_id, team_id, date)
        return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving costs: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/anomalies", response_model=List[CostAnomaly])
async def get_anomalies(
    request: Request,
    authorization: Optional[str] = Header(None),
    team_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(1000, ge=1, le=10000)
) -> List[CostAnomaly]:
    """
    Get detected cost anomalies.
    
    Args:
        request: FastAPI request
        authorization: Authorization header
        team_id: Filter by team ID
        severity: Filter by severity (critical, warning, info)
        active_only: Only return active anomalies
        limit: Max results
        
    Returns:
        List of anomalies
    """
    try:
        user_id, user_role = _get_user_from_header(request, authorization)
        ip_address = request.client.host if request.client else None
        
        # Authorization check
        if not access_control.can_view_anomalies(user_id, user_role, "all", team_id, ip_address):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # In production: query from repository
        # return repository.get_anomalies(team_id, severity, active_only, limit)
        
        logger.info("Retrieved anomalies: user=%s, team=%s, severity=%s, active=%s", 
                   user_id, team_id, severity, active_only)
        return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving anomalies: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/anomalies/{anomaly_id}/acknowledge", response_model=Dict[str, Any])
async def acknowledge_anomaly(
    anomaly_id: str,
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Acknowledge a cost anomaly.
    
    Args:
        anomaly_id: Anomaly ID
        request: FastAPI request
        authorization: Authorization header
        
    Returns:
        Acknowledgment result
    """
    try:
        user_id, user_role = _get_user_from_header(request, authorization)
        ip_address = request.client.host if request.client else None
        
        # Authorization check
        if not access_control.can_view_anomalies(user_id, user_role, anomaly_id, ip_address=ip_address):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # In production: update repository
        # repository.acknowledge_anomaly(anomaly_id)
        
        logger.info("Acknowledged anomaly: user=%s, anomaly=%s", user_id, anomaly_id)
        return {"anomaly_id": anomaly_id, "acknowledged": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error acknowledging anomaly: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/forecast", response_model=List[CostForecast])
async def get_forecast(
    request: Request,
    authorization: Optional[str] = Header(None),
    resource_id: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=90),
    limit: int = Query(1000, ge=1, le=10000)
) -> List[CostForecast]:
    """
    Get cost forecasts.
    
    Args:
        request: FastAPI request
        authorization: Authorization header
        resource_id: Filter by resource ID
        days: Forecast period (7, 14, 30, 60, 90)
        limit: Max results
        
    Returns:
        List of forecasts
    """
    try:
        user_id, user_role = _get_user_from_header(request, authorization)
        ip_address = request.client.host if request.client else None
        
        # Authorization check (forecast is service-level)
        if not access_control.can_view_cost(user_id, user_role, "forecast", 
                                           resource_id or "all", ip_address=ip_address):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # In production: query from repository
        # return repository.get_forecasts(resource_id, days, limit)
        
        logger.info("Retrieved forecasts: user=%s, resource=%s, days=%d", user_id, resource_id, days)
        return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving forecasts: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/by-team", response_model=List[CostByTeam])
async def get_costs_by_team(
    request: Request,
    authorization: Optional[str] = Header(None),
    date: Optional[str] = Query(None)
) -> List[CostByTeam]:
    """
    Get costs aggregated by team.
    
    Args:
        request: FastAPI request
        authorization: Authorization header
        date: Filter by date (YYYY-MM-DD)
        
    Returns:
        List of team cost aggregates
    """
    try:
        user_id, user_role = _get_user_from_header(request, authorization)
        ip_address = request.client.host if request.client else None
        
        # Authorization check
        if not access_control.can_view_cost(user_id, user_role, "team", "all", ip_address=ip_address):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # In production: query from repository
        # return repository.get_team_costs(date)
        
        logger.info("Retrieved team costs: user=%s, date=%s", user_id, date)
        return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving team costs: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/access-log", response_model=List[CostAccessLog])
async def get_access_log(
    request: Request,
    authorization: Optional[str] = Header(None),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=10000)
) -> List[CostAccessLog]:
    """
    Get access logs (admin only).
    
    Args:
        request: FastAPI request
        authorization: Authorization header
        user_id: Filter by user
        action: Filter by action
        limit: Max results
        
    Returns:
        List of access logs
    """
    try:
        admin_user, admin_role = _get_user_from_header(request, authorization)
        
        # Admin check
        if admin_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # In production: query from repository
        # return repository.get_access_logs(user_id, action, limit=limit)
        
        logger.info("Retrieved access logs: admin=%s, filter_user=%s, action=%s", 
                   admin_user, user_id, action)
        return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving access logs: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/ingest", response_model=Dict[str, Any])
async def ingest_billing_data(
    request: Request,
    authorization: Optional[str] = Header(None),
    start_date: str = Query(...),
    end_date: str = Query(...),
    providers: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Trigger billing data ingestion (admin only).
    
    Args:
        request: FastAPI request
        authorization: Authorization header
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        providers: Comma-separated providers (aws, azure, gcp)
        
    Returns:
        Ingestion result
    """
    try:
        user_id, user_role = _get_user_from_header(request, authorization)
        
        # Admin check
        if user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Parse dates
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        # In production: run agent pipeline
        # result = await agent.run_pipeline(start, end)
        
        logger.info("Ingested billing data: user=%s, period=%s to %s", user_id, start_date, end_date)
        return {
            "status": "success",
            "start_date": start_date,
            "end_date": end_date,
            "items_ingested": 0
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error ingesting billing data: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
