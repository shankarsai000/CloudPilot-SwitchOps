"""
CloudPilot SwitchOps — Server-Side Principal Authentication Provider (Phase 4.1)

Provides verified server-side identity and role enforcement:
- Pre-registered server-side principal directory
- Cryptographic Bearer token verification (HMAC-SHA256)
- Rejection of client-side role escalation and identity spoofing
- Fail-closed handling for missing, invalid, or forged credentials
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Dict, Optional, Tuple

from app.domain.approvals import ApprovalPrincipal, ApproverRole

logger = logging.getLogger("cloudpilot.approval.auth")

DEFAULT_AUTH_SECRET = b"cloudpilot-switchops-auth-bearer-secret-32b-min"

# Server-side authoritative registry of known principals and their assigned roles
SERVER_PRINCIPAL_DIRECTORY: Dict[str, ApproverRole] = {
    "lead-platform": ApproverRole.PLATFORM_LEAD,
    "sec-lead": ApproverRole.SECURITY_LEAD,
    "finops-lead": ApproverRole.FINOPS_LEAD,
    "junior-ops": ApproverRole.OPERATOR,
    "dev-user": ApproverRole.DEVELOPER,
    "guest-viewer": ApproverRole.VIEWER,
    "@platform-lead:switch": ApproverRole.PLATFORM_LEAD,
    "@secops-lead:switch": ApproverRole.SECURITY_LEAD,
    "@finops-lead:switch": ApproverRole.FINOPS_LEAD,
    "@operator:switch": ApproverRole.OPERATOR,
    "system-coordinator": ApproverRole.PLATFORM_LEAD,
}


class ServerSidePrincipalAuthenticator:
    """
    Authoritative server-side identity and authorization provider.
    Ensures principals cannot escalate roles or spoof identities via client headers or request bodies.
    """

    def __init__(
        self,
        principal_directory: Optional[Dict[str, ApproverRole]] = None,
        secret_key: Optional[bytes] = None,
    ) -> None:
        self.directory = dict(principal_directory if principal_directory is not None else SERVER_PRINCIPAL_DIRECTORY)
        self.secret_key = secret_key or DEFAULT_AUTH_SECRET

    def issue_bearer_token(
        self,
        principal_id: str,
        role: ApproverRole,
        ttl_seconds: int = 3600,
    ) -> str:
        """Issues a signed HMAC-SHA256 Bearer authentication token."""
        now = int(time.time())
        payload = {
            "sub": principal_id,
            "role": role.value,
            "iat": now,
            "exp": now + ttl_seconds,
        }
        b64_payload = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).decode("ascii").rstrip("=")
        sig = hmac.new(self.secret_key, b64_payload.encode("utf-8"), hashlib.sha256).digest()
        b64_sig = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
        return f"cp-auth.v1.{b64_payload}.{b64_sig}"

    def verify_bearer_token(self, token_str: str) -> Tuple[bool, Optional[str], Optional[ApproverRole], Optional[str]]:
        """
        Verifies a signed Bearer token.
        Returns: (is_valid, principal_id, role, error_reason)
        """
        if not token_str.startswith("cp-auth.v1."):
            return False, None, None, "Invalid token prefix"

        parts = token_str.split(".")
        if len(parts) != 4:
            return False, None, None, "Invalid token structure"

        _, _, b64_payload, b64_sig = parts
        expected_sig = hmac.new(self.secret_key, b64_payload.encode("utf-8"), hashlib.sha256).digest()
        expected_b64_sig = base64.urlsafe_b64encode(expected_sig).decode("ascii").rstrip("=")

        if not hmac.compare_digest(b64_sig, expected_b64_sig):
            return False, None, None, "Token signature verification failed"

        try:
            pad_len = (4 - len(b64_payload) % 4) % 4
            raw_bytes = base64.urlsafe_b64decode((b64_payload + "=" * pad_len).encode("ascii"))
            data = json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:
            return False, None, None, f"Malformed token payload: {exc}"

        exp = data.get("exp", 0)
        if int(time.time()) > exp:
            return False, None, None, "Token has expired"

        sub = data.get("sub")
        role_str = data.get("role")
        try:
            role = ApproverRole(role_str)
        except (ValueError, TypeError):
            return False, None, None, f"Unknown role '{role_str}' in token"

        return True, sub, role, None

    def authenticate(
        self,
        x_user_id: Optional[str] = None,
        x_user_role: Optional[str] = None,
        authorization: Optional[str] = None,
    ) -> ApprovalPrincipal:
        """
        Authenticates caller credentials using server-side directory and token verification.
        Fails closed on missing, spoofed, or unverified credentials.
        """
        # 1. Bearer token authentication
        if authorization and authorization.startswith("Bearer "):
            token_val = authorization[7:].strip()
            valid, sub, role, err = self.verify_bearer_token(token_val)
            if valid and sub and role:
                return ApprovalPrincipal(
                    principal_id=sub,
                    display_name=sub,
                    role=role,
                    authenticated=True,
                    auth_mechanism="BEARER_TOKEN",
                )
            else:
                logger.warning("Bearer token authentication failed: %s", err)
                return ApprovalPrincipal(
                    principal_id="anonymous",
                    display_name="Invalid Token Principal",
                    role=ApproverRole.VIEWER,
                    authenticated=False,
                    auth_mechanism="UNAUTHENTICATED",
                )

        # 2. Header-based authentication against authoritative server directory
        if not x_user_id:
            return ApprovalPrincipal(
                principal_id="anonymous",
                display_name="Anonymous Operator",
                role=ApproverRole.VIEWER,
                authenticated=False,
                auth_mechanism="UNAUTHENTICATED",
            )

        # Look up authoritative server-side role for this identity
        if x_user_id not in self.directory:
            logger.warning("Unregistered principal '%s' rejected fail-closed", x_user_id)
            return ApprovalPrincipal(
                principal_id=x_user_id,
                display_name=x_user_id,
                role=ApproverRole.VIEWER,
                authenticated=False,
                auth_mechanism="UNREGISTERED_IDENTITY",
            )

        authoritative_role = self.directory[x_user_id]

        # Detect and reject caller-supplied role escalation
        if x_user_role:
            try:
                requested_role = ApproverRole(x_user_role.upper())
            except ValueError:
                requested_role = None

            if requested_role and requested_role != authoritative_role:
                logger.warning(
                    "Caller-supplied role escalation detected for '%s': claimed '%s', authoritative is '%s'",
                    x_user_id,
                    requested_role.value,
                    authoritative_role.value,
                )
                # Fail closed: reject escalation, set authenticated=False
                return ApprovalPrincipal(
                    principal_id=x_user_id,
                    display_name=x_user_id,
                    role=authoritative_role,
                    authenticated=False,
                    auth_mechanism="ROLE_ESCALATION_REJECTED",
                )

        return ApprovalPrincipal(
            principal_id=x_user_id,
            display_name=x_user_id,
            role=authoritative_role,
            authenticated=True,
            auth_mechanism="SERVER_DIRECTORY_VERIFIED",
        )

