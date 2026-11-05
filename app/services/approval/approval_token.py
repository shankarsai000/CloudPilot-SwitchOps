"""
CloudPilot SwitchOps — Approval Token Cryptographic Manager (Phase 4)

Manages generation, serialization, HMAC-SHA256 signing, and constant-time
signature verification for human approval tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional, Tuple

from app.core.config import get_settings
from app.domain.approvals import ApprovalTokenPayload

logger = logging.getLogger("cloudpilot.approval.token")


class ApprovalTokenManager:
    """
    Issues and cryptographically validates tamper-evident, unforgeable approval tokens.
    Uses HMAC-SHA256 with constant-time verification to prevent timing attacks.
    """

    def __init__(self, secret_key: Optional[bytes] = None) -> None:
        if secret_key:
            self._secret_key = secret_key
        else:
            settings = get_settings()
            secret_str = getattr(settings, "approval_hmac_secret", None)
            if secret_str and hasattr(secret_str, "get_secret_value"):
                self._secret_key = secret_str.get_secret_value().encode("utf-8")
            elif secret_str and isinstance(secret_str, str):
                self._secret_key = secret_str.encode("utf-8")
            else:
                # Default secure fallback for testing/dev environments (at least 32 bytes)
                self._secret_key = b"cloudpilot-switchops-hmac-sha256-approval-secret-32b-min"

    def issue_token(
        self,
        proposal_id: str,
        proposal_hash: str,
        approver_id: str,
        approver_role: str,
        decision_id: str,
        task_id: str,
        ttl_seconds: int = 3600,
    ) -> Tuple[str, ApprovalTokenPayload]:
        """
        Creates, signs, and formats an approval token.
        Token format: v1.<token_id>.<b64_payload>.<b64_signature>
        """
        now = int(time.time())
        token_id = f"tok-{secrets.token_hex(8)}"
        payload = ApprovalTokenPayload(
            token_id=token_id,
            proposal_id=proposal_id,
            proposal_hash=proposal_hash,
            approver_id=approver_id,
            approver_role=approver_role,
            decision_id=decision_id,
            task_id=task_id,
            issued_at=now,
            expires_at=now + ttl_seconds,
        )

        canonical_json = json.dumps(payload.model_dump(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(canonical_json).decode("ascii").rstrip("=")

        # Compute HMAC-SHA256 signature over token_id + "." + b64_payload
        sign_target = f"{token_id}.{b64_payload}".encode("utf-8")
        signature = hmac.new(self._secret_key, sign_target, hashlib.sha256).digest()
        b64_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")

        token_string = f"v1.{token_id}.{b64_payload}.{b64_signature}"
        return token_string, payload

    def verify_token(
        self,
        token_string: str,
        current_time: Optional[int] = None,
    ) -> Tuple[bool, Optional[ApprovalTokenPayload], Optional[str]]:
        """
        Verifies token structure, signature, and expiration.
        Uses constant-time comparison to protect against timing attacks.
        Returns: (is_valid, payload, error_reason)
        """
        if not token_string or not isinstance(token_string, str):
            return False, None, "Token string is empty or invalid"

        parts = token_string.split(".")
        if len(parts) != 4:
            return False, None, "Invalid token structure (expected 4 dot-separated segments)"

        version, token_id, b64_payload, b64_signature = parts
        if version != "v1":
            return False, None, f"Unsupported token version '{version}'"

        # Re-compute expected signature
        sign_target = f"{token_id}.{b64_payload}".encode("utf-8")
        expected_sig_bytes = hmac.new(self._secret_key, sign_target, hashlib.sha256).digest()
        expected_b64_sig = base64.urlsafe_b64encode(expected_sig_bytes).decode("ascii").rstrip("=")

        # Constant-time comparison
        if not hmac.compare_digest(b64_signature, expected_b64_sig):
            return False, None, "Cryptographic signature verification failed (token forged or tampered)"

        # Decode payload
        try:
            # Re-pad base64url string if needed
            pad_len = (4 - len(b64_payload) % 4) % 4
            padded_b64 = b64_payload + "=" * pad_len
            raw_bytes = base64.urlsafe_b64decode(padded_b64.encode("ascii"))
            data = json.loads(raw_bytes.decode("utf-8"))
            payload = ApprovalTokenPayload(**data)
        except Exception as exc:
            return False, None, f"Malformed token payload: {exc}"

        # Verify token_id matches
        if payload.token_id != token_id:
            return False, None, "Token ID segment mismatch"

        # Expiration check
        now_ts = current_time if current_time is not None else int(time.time())
        if now_ts > payload.expires_at:
            return False, payload, f"Approval token has expired (expired at {payload.expires_at}, now={now_ts})"

        return True, payload, None
