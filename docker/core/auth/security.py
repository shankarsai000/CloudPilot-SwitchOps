"""
Security primitives: JWT token generation, verification, and password hashing.
"""

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import jwt
from pydantic import BaseModel, Field

from core.config import get_settings
from core.errors import AuthenticationError


class TokenPayload(BaseModel):
    """Decoded JWT payload representation."""
    sub: str = Field(description="User identifier")
    username: str = Field(description="Username")
    role: str = Field(default="viewer", description="Assigned RBAC role")
    permissions: List[str] = Field(default_factory=list, description="Granted granular permissions")
    exp: int = Field(description="Expiration Unix timestamp")
    iat: int = Field(description="Issued at Unix timestamp")


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """
    Hash a plaintext password using PBKDF2-HMAC-SHA256 with 100,000 rounds.
    
    Returns:
        Salt and hash combined as hex: 'salt_hex$hash_hex'
    """
    if salt is None:
        salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${hashed.hex()}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verify a plain password against stored 'salt$hash'."""
    try:
        salt_hex, hash_hex = stored_hash.split("$")
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
        candidate_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(expected_hash, candidate_hash)
    except Exception:
        return False


def create_access_token(
    subject: str,
    username: str,
    role: str,
    permissions: Optional[List[str]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_expiration_minutes)

    payload: Dict[str, Any] = {
        "sub": subject,
        "username": username,
        "role": role,
        "permissions": permissions or [],
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }

    token = jwt.encode(
        payload,
        settings.get_jwt_secret(),
        algorithm=settings.jwt_algorithm,
    )
    return token


def decode_access_token(token: str) -> TokenPayload:
    """
    Validate and decode a JWT access token.
    
    Raises:
        AuthenticationError: If token is invalid or expired
    """
    settings = get_settings()
    try:
        decoded = jwt.decode(
            token,
            settings.get_jwt_secret(),
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(**decoded)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"Invalid access token: {exc}") from exc
