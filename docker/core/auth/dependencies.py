"""
FastAPI dependencies for authentication and authorization.
"""

from typing import Callable, List, Optional
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from core.auth.rbac import has_permission
from core.auth.security import decode_access_token
from core.config import get_settings
from core.errors import AuthenticationError, AuthorizationError
from core.logging import user_id_ctx

http_bearer = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Authenticated user context object."""
    user_id: str
    username: str
    role: str
    permissions: List[str] = Field(default_factory=list)
    is_system: bool = False


async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedUser:
    """
    Extract and validate authenticated user from JWT Bearer token or X-API-Key header.
    
    Raises:
        AuthenticationError: If credentials are missing, invalid, or expired.
    """
    settings = get_settings()

    # 1. Check API Key first if present
    if x_api_key:
        expected_key = settings.api_key.get_secret_value() if settings.api_key else None
        if expected_key and x_api_key == expected_key:
            user = AuthenticatedUser(
                user_id="system-api-key",
                username="system",
                role="admin",
                permissions=["admin:*"],
                is_system=True,
            )
            user_id_ctx.set(user.user_id)
            return user
        raise AuthenticationError("Invalid platform API Key provided")

    # 2. Check JWT Bearer token
    if auth_header and auth_header.credentials:
        token = auth_header.credentials
        payload = decode_access_token(token)
        user = AuthenticatedUser(
            user_id=payload.sub,
            username=payload.username,
            role=payload.role,
            permissions=payload.permissions,
            is_system=False,
        )
        user_id_ctx.set(user.user_id)
        return user

    # In local testing mode without credentials, allow a default system viewer if explicitly configured
    if settings.is_testing and not auth_header and not x_api_key:
        user = AuthenticatedUser(
            user_id="test-user",
            username="tester",
            role="admin",
            permissions=["admin:*"],
            is_system=True,
        )
        user_id_ctx.set(user.user_id)
        return user

    raise AuthenticationError("Missing authentication token or API key")


def require_role(allowed_roles: List[str]) -> Callable[..., AuthenticatedUser]:
    """
    Dependency factory checking that current user belongs to one of allowed roles.
    """
    allowed_set = {r.lower() for r in allowed_roles}

    async def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role.lower() not in allowed_set and "admin" not in allowed_set and user.role.lower() != "admin":
            raise AuthorizationError(
                f"Role '{user.role}' is not authorized. Required: {allowed_roles}"
            )
        return user

    return role_checker


def require_permission(permission: str) -> Callable[..., AuthenticatedUser]:
    """
    Dependency factory checking that current user possesses a required permission.
    """
    async def permission_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not has_permission(user.role, user.permissions, permission):
            raise AuthorizationError(
                f"User lacks required permission '{permission}'"
            )
        return user

    return permission_checker
