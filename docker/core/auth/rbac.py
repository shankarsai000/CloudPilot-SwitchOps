"""
Role-Based Access Control (RBAC) definition and permission validation.
"""

from enum import Enum
from typing import Dict, List, Set


class Role(str, Enum):
    """Platform RBAC Roles."""
    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    VIEWER = "viewer"
    SYSTEM = "system"


class Permission(str, Enum):
    """Granular platform operation permissions."""
    # Discovery (M1)
    DISCOVERY_READ = "discovery:read"
    DISCOVERY_WRITE = "discovery:write"

    # Cost Intelligence (M2)
    COST_READ = "cost:read"
    COST_WRITE = "cost:write"

    # Application Intelligence (M3)
    APP_READ = "application:read"
    APP_WRITE = "application:write"

    # Risk Intelligence (M4)
    RISK_READ = "risk:read"
    RISK_WRITE = "risk:write"

    # Strategy (M5)
    STRATEGY_READ = "strategy:read"
    STRATEGY_WRITE = "strategy:write"

    # Digital Twin & Simulation (M6)
    SIMULATION_READ = "simulation:read"
    SIMULATION_RUN = "simulation:run"

    # Explainability (M7)
    EXPLANATION_READ = "explanation:read"

    # Learning (M8)
    LEARNING_READ = "learning:read"
    LEARNING_FEEDBACK = "learning:feedback"

    # Decision Engine (M9)
    DECISION_READ = "decision:read"
    DECISION_APPROVE = "decision:approve"
    DECISION_OVERRIDE = "decision:override"

    # Execution Engine (M10)
    EXECUTION_READ = "execution:read"
    EXECUTION_RUN = "execution:run"
    EXECUTION_ROLLBACK = "execution:rollback"

    # Administrative
    ADMIN_ALL = "admin:*"


ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    Role.ADMIN.value: {
        Permission.ADMIN_ALL.value,
        Permission.DISCOVERY_READ.value,
        Permission.DISCOVERY_WRITE.value,
        Permission.COST_READ.value,
        Permission.COST_WRITE.value,
        Permission.APP_READ.value,
        Permission.APP_WRITE.value,
        Permission.RISK_READ.value,
        Permission.RISK_WRITE.value,
        Permission.STRATEGY_READ.value,
        Permission.STRATEGY_WRITE.value,
        Permission.SIMULATION_READ.value,
        Permission.SIMULATION_RUN.value,
        Permission.EXPLANATION_READ.value,
        Permission.LEARNING_READ.value,
        Permission.LEARNING_FEEDBACK.value,
        Permission.DECISION_READ.value,
        Permission.DECISION_APPROVE.value,
        Permission.DECISION_OVERRIDE.value,
        Permission.EXECUTION_READ.value,
        Permission.EXECUTION_RUN.value,
        Permission.EXECUTION_ROLLBACK.value,
    },
    Role.OPERATOR.value: {
        Permission.DISCOVERY_READ.value,
        Permission.DISCOVERY_WRITE.value,
        Permission.COST_READ.value,
        Permission.APP_READ.value,
        Permission.RISK_READ.value,
        Permission.STRATEGY_READ.value,
        Permission.SIMULATION_READ.value,
        Permission.SIMULATION_RUN.value,
        Permission.EXPLANATION_READ.value,
        Permission.LEARNING_READ.value,
        Permission.DECISION_READ.value,
        Permission.DECISION_APPROVE.value,
        Permission.EXECUTION_READ.value,
        Permission.EXECUTION_RUN.value,
        Permission.EXECUTION_ROLLBACK.value,
    },
    Role.ANALYST.value: {
        Permission.DISCOVERY_READ.value,
        Permission.COST_READ.value,
        Permission.APP_READ.value,
        Permission.RISK_READ.value,
        Permission.STRATEGY_READ.value,
        Permission.SIMULATION_READ.value,
        Permission.EXPLANATION_READ.value,
        Permission.LEARNING_READ.value,
        Permission.LEARNING_FEEDBACK.value,
        Permission.DECISION_READ.value,
        Permission.EXECUTION_READ.value,
    },
    Role.VIEWER.value: {
        Permission.DISCOVERY_READ.value,
        Permission.COST_READ.value,
        Permission.APP_READ.value,
        Permission.RISK_READ.value,
        Permission.STRATEGY_READ.value,
        Permission.SIMULATION_READ.value,
        Permission.EXPLANATION_READ.value,
        Permission.LEARNING_READ.value,
        Permission.DECISION_READ.value,
        Permission.EXECUTION_READ.value,
    },
    Role.SYSTEM.value: {
        Permission.ADMIN_ALL.value,
    },
}


def has_permission(user_role: str, user_permissions: List[str], required_permission: str) -> bool:
    """
    Check if a user possesses the required permission either through their role
    or direct permission grants. Admin / wildcards grant universal access.
    """
    role_norm = user_role.lower()
    role_perms = ROLE_PERMISSIONS.get(role_norm, set())

    # Check wildcard
    if Permission.ADMIN_ALL.value in role_perms or Permission.ADMIN_ALL.value in user_permissions:
        return True

    # Check direct role permission
    if required_permission in role_perms:
        return True

    # Check user explicit permission
    if required_permission in user_permissions:
        return True

    return False
