"""
Cost Access Control - Authorization and audit logging
Who can view which cost data, audit logging
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any

from models_cost import CostAccessLog

logger = logging.getLogger(__name__)


class CostAccessControl:
    """Authorization and audit logging for cost data access."""
    
    # Permission model: user_role -> allowed_resource_types
    ROLE_PERMISSIONS = {
        'admin': ['team', 'service', 'resource', 'anomaly', 'forecast'],
        'manager': ['team', 'service', 'anomaly'],
        'engineer': ['team'],
        'viewer': []
    }
    
    # Team membership: user_id -> [team_ids]
    USER_TEAMS: Dict[str, List[str]] = {}
    
    def __init__(self) -> None:
        """Initialize access control."""
        logger.info("Cost access control initialized")
    
    def register_user_teams(self, user_id: str, team_ids: List[str]) -> None:
        """
        Register user's team memberships.
        
        Args:
            user_id: User ID
            team_ids: List of team IDs user belongs to
        """
        self.USER_TEAMS[user_id] = team_ids
        logger.debug("Registered user %s with %d teams", user_id, len(team_ids))
    
    def can_view_cost(
        self,
        user_id: str,
        user_role: str,
        resource_type: str,
        resource_id: str,
        team_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Check if user can view cost data.
        
        Args:
            user_id: User ID
            user_role: User role (admin, manager, engineer, viewer)
            resource_type: Type of resource (team, service, resource, anomaly, forecast)
            resource_id: Resource ID
            team_id: Team ID (required for non-admin roles)
            ip_address: User IP address
            
        Returns:
            True if access allowed, False otherwise
        """
        try:
            # Check role permissions
            allowed_types = self.ROLE_PERMISSIONS.get(user_role, [])
            if resource_type not in allowed_types:
                logger.warning("Access denied: user=%s, role=%s, type=%s (not in role permissions)",
                              user_id, user_role, resource_type)
                self._log_access(user_id, "view_costs", resource_type, resource_id, False, ip_address)
                return False
            
            # Admin can view everything
            if user_role == 'admin':
                logger.debug("Access allowed: user=%s (admin)", user_id)
                self._log_access(user_id, "view_costs", resource_type, resource_id, True, ip_address)
                return True
            
            # For non-admin: check team membership
            if not team_id:
                logger.warning("Access denied: user=%s, team_id required for role=%s", user_id, user_role)
                self._log_access(user_id, "view_costs", resource_type, resource_id, False, ip_address)
                return False
            
            user_teams = self.USER_TEAMS.get(user_id, [])
            if team_id not in user_teams:
                logger.warning("Access denied: user=%s not in team=%s", user_id, team_id)
                self._log_access(user_id, "view_costs", resource_type, resource_id, False, ip_address)
                return False
            
            logger.debug("Access allowed: user=%s, team=%s, type=%s", user_id, team_id, resource_type)
            self._log_access(user_id, "view_costs", resource_type, resource_id, True, ip_address)
            return True
            
        except Exception as e:
            logger.error("Error checking access: %s", str(e))
            self._log_access(user_id, "view_costs", resource_type, resource_id, False, ip_address)
            return False
    
    def can_export_costs(
        self,
        user_id: str,
        user_role: str,
        resource_type: str,
        resource_id: str,
        team_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Check if user can export cost data.
        
        Args:
            user_id: User ID
            user_role: User role
            resource_type: Type of resource
            resource_id: Resource ID
            team_id: Team ID
            ip_address: User IP address
            
        Returns:
            True if export allowed, False otherwise
        """
        # Only admin and manager can export
        if user_role not in ['admin', 'manager']:
            logger.warning("Export denied: user=%s, role=%s (insufficient permissions)", user_id, user_role)
            self._log_access(user_id, "export_costs", resource_type, resource_id, False, ip_address)
            return False
        
        # Check team membership for manager
        if user_role == 'manager' and team_id:
            user_teams = self.USER_TEAMS.get(user_id, [])
            if team_id not in user_teams:
                logger.warning("Export denied: user=%s not in team=%s", user_id, team_id)
                self._log_access(user_id, "export_costs", resource_type, resource_id, False, ip_address)
                return False
        
        logger.info("Export allowed: user=%s, role=%s", user_id, user_role)
        self._log_access(user_id, "export_costs", resource_type, resource_id, True, ip_address)
        return True
    
    def can_view_anomalies(
        self,
        user_id: str,
        user_role: str,
        anomaly_id: str,
        team_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Check if user can view anomalies.
        
        Args:
            user_id: User ID
            user_role: User role
            anomaly_id: Anomaly ID
            team_id: Team ID
            ip_address: User IP address
            
        Returns:
            True if access allowed, False otherwise
        """
        # Only admin, manager, engineer can view anomalies
        if user_role == 'viewer':
            logger.warning("Anomaly access denied: user=%s, role=viewer", user_id)
            self._log_access(user_id, "view_anomalies", "anomaly", anomaly_id, False, ip_address)
            return False
        
        # Engineer can only view team anomalies
        if user_role == 'engineer' and team_id:
            user_teams = self.USER_TEAMS.get(user_id, [])
            if team_id not in user_teams:
                logger.warning("Anomaly access denied: user=%s not in team=%s", user_id, team_id)
                self._log_access(user_id, "view_anomalies", "anomaly", anomaly_id, False, ip_address)
                return False
        
        logger.debug("Anomaly access allowed: user=%s, anomaly=%s", user_id, anomaly_id)
        self._log_access(user_id, "view_anomalies", "anomaly", anomaly_id, True, ip_address)
        return True
    
    def _log_access(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        allowed: bool,
        ip_address: Optional[str] = None
    ) -> None:
        """
        Log access attempt (internal).
        
        Args:
            user_id: User ID
            action: Action (view_costs, export_costs, view_anomalies, etc.)
            resource_type: Resource type
            resource_id: Resource ID
            allowed: Whether access was allowed
            ip_address: User IP address
        """
        try:
            log = CostAccessLog(
                log_id=str(uuid.uuid4()),
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                allowed=allowed,
                ip_address=ip_address
            )
            
            level = "allowed" if allowed else "denied"
            logger.info("Access %s: user=%s, action=%s, resource=%s/%s", 
                       level, user_id, action, resource_type, resource_id)
            
            # In production: persist to database via repository
            
        except Exception as e:
            logger.error("Error logging access: %s", str(e))
    
    def get_access_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        allowed_only: Optional[bool] = None,
        limit: int = 1000
    ) -> List[CostAccessLog]:
        """
        Retrieve access logs.
        
        Args:
            user_id: Filter by user
            action: Filter by action
            allowed_only: Filter by success
            limit: Max results
            
        Returns:
            List of access logs
        """
        try:
            logger.debug("Querying access logs (user=%s, action=%s, allowed=%s)",
                        user_id, action, allowed_only)
            # In production: query from database
            return []
        except Exception as e:
            logger.error("Error retrieving access logs: %s", str(e))
            raise
