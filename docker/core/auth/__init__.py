"""
Authentication and Role-Based Access Control (RBAC) foundation.
"""

from core.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    TokenPayload,
)
from core.auth.rbac import (
    Role,
    Permission,
    ROLE_PERMISSIONS,
    has_permission,
)
from core.auth.dependencies import (
    get_current_user,
    require_permission,
    require_role,
    AuthenticatedUser,
)

__all__ = [
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
    "TokenPayload",
    "Role",
    "Permission",
    "ROLE_PERMISSIONS",
    "has_permission",
    "get_current_user",
    "require_permission",
    "require_role",
    "AuthenticatedUser",
]
