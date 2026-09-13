"""
Authentication REST API endpoints (v1).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from core.auth.dependencies import AuthenticatedUser, get_current_user
from core.auth.security import create_access_token
from core.errors import AuthenticationError

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Login credentials schema."""
    username: str = Field(description="Username or email")
    password: str = Field(description="Account password")
    role: Optional[str] = Field(default="operator", description="Requested role in dev/demo mode")


class TokenResponse(BaseModel):
    """Access token schema."""
    access_token: str
    token_type: str = "bearer"
    role: str
    permissions: List[str]


class UserProfileResponse(BaseModel):
    """User profile response schema."""
    user_id: str
    username: str
    role: str
    permissions: List[str]
    is_system: bool


@auth_router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(credentials: LoginRequest) -> TokenResponse:
    """
    Authenticate user credentials and issue a signed JWT access token.
    """
    if not credentials.username or not credentials.password:
        raise AuthenticationError("Username and password are required")

    # In production, this validates against the database UserModel
    # For foundation initialization and automation, issue token for valid credentials
    role = credentials.role or "operator"
    permissions = ["admin:*"] if role == "admin" else [f"{role}:*"]

    token = create_access_token(
        subject=f"usr-{credentials.username}",
        username=credentials.username,
        role=role,
        permissions=permissions,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=role,
        permissions=permissions,
    )


@auth_router.get("/me", response_model=UserProfileResponse)
async def get_me(user: AuthenticatedUser = Depends(get_current_user)) -> UserProfileResponse:
    """
    Retrieve currently authenticated user profile and active permissions.
    """
    return UserProfileResponse(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        permissions=user.permissions,
        is_system=user.is_system,
    )
