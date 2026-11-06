"""
CloudPilot SwitchOps — Switch Inbound Event Handler & Identity Boundary (Phase 4.2)

Validates incoming Switch wire protocol frames, deduplicates message events,
extracts correlated proposal approval/rejection commands, and enforces the
Switch-to-CloudPilot authentication boundary (never trusting display names or client roles).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from app.domain.approvals import ApprovalPrincipal, ApproverRole
from app.integrations.switch.exceptions import SwitchProtocolError

if TYPE_CHECKING:
    from app.services.approval.auth_provider import ServerSidePrincipalAuthenticator

logger = logging.getLogger("cloudpilot.integrations.switch.event_handler")

SUPPORTED_FRAME_TYPES = {"connection_state", "ping", "pong", "event", "evicted"}


class SwitchEventHandler:
    """
    Validates Switch protocol frames and enforces the strict Switch-to-CloudPilot
    authentication and correlation boundary.
    """

    def __init__(
        self,
        authenticator: Optional[Any] = None,
    ) -> None:
        if authenticator is None:
            from app.services.approval.auth_provider import ServerSidePrincipalAuthenticator

            self.authenticator = ServerSidePrincipalAuthenticator()
        else:
            self.authenticator = authenticator

    @staticmethod
    def validate_frame(frame: Any) -> Dict[str, Any]:
        """
        Validates that a received frame conforms to the Switch Agent Bridge wire protocol.
        Raises SwitchProtocolError on malformed frames.
        """
        if not isinstance(frame, dict):
            raise SwitchProtocolError("Switch frame must be a JSON object dictionary.")

        frame_type = frame.get("type") or ("event" if "event" in frame else None)
        if not frame_type or frame_type not in SUPPORTED_FRAME_TYPES:
            raise SwitchProtocolError(
                f"Unsupported or missing Switch frame type '{frame_type}'. "
                f"Supported: {sorted(SUPPORTED_FRAME_TYPES)}"
            )
        if "type" not in frame and frame_type:
            frame["type"] = frame_type

        if frame_type == "event":
            payload = frame.get("payload")
            if not isinstance(payload, dict):
                raise SwitchProtocolError("Switch 'event' frame is missing a valid 'payload' dictionary.")

        return frame

    def resolve_authenticated_principal(
        self,
        sender: str,
        sender_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalPrincipal:
        """
        Enforces Workstream D3 (Switch-to-CloudPilot Authentication Boundary):
        - Never trusts display names (sender_name) for role assignment.
        - Never trusts unverified participant metadata (user_role) for role escalation.
        - Resolves identity strictly against ServerSidePrincipalAuthenticator.
        - If Switch identity cannot be linked to a registered server-side principal
          or verified cryptographic Bearer token, fails closed with authenticated=False.
        """
        meta = metadata or {}
        auth_header = meta.get("authorization") or meta.get("Authorization")
        claimed_role = meta.get("user_role") or meta.get("approver_role")

        # 1. If a cryptographic Bearer token is supplied, authenticate via token
        if auth_header and str(auth_header).startswith("Bearer "):
            principal = self.authenticator.authenticate(authorization=str(auth_header))
            if principal.authenticated:
                return ApprovalPrincipal(
                    principal_id=principal.principal_id,
                    display_name=sender_name or principal.display_name,
                    role=principal.role,
                    authenticated=True,
                    auth_mechanism="BEARER_TOKEN",
                )
            return principal

        # 2. Verify Switch sender handle against authoritative server-side directory
        principal = self.authenticator.authenticate(
            x_user_id=sender,
            x_user_role=str(claimed_role) if claimed_role else None,
        )
        return ApprovalPrincipal(
            principal_id=principal.principal_id,
            display_name=sender_name or principal.display_name,
            role=principal.role,
            authenticated=principal.authenticated,
            auth_mechanism=principal.auth_mechanism,
        )

    @staticmethod
    def parse_approval_command(body: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
        """
        Parses a Switch approval command:
        '@cloudpilot-ops-agent approve proposal prop-xxxx [hash <sha256>] [token <token>]'
        Returns: (proposal_id, provided_hash, token_str) or None.
        """
        if not re.search(r"\bapprove\b", body, re.IGNORECASE):
            return None
        prop_match = re.search(r"\b(prop-[a-zA-Z0-9_-]+)\b", body)
        if not prop_match:
            return None
        proposal_id = prop_match.group(1)

        hash_match = re.search(r"\bhash[:\s]+([a-fA-F0-9]{16,64})\b", body, re.IGNORECASE)
        provided_hash = hash_match.group(1).lower() if hash_match else None

        tok_match = re.search(r"\btoken[:\s]+(v1\.[^\s]+)\b", body, re.IGNORECASE)
        if not tok_match:
            # Check trailing token if not prefixed by 'hash'
            fallback_tok = re.search(
                r"\bapprove(?:\s+proposal)?\s+prop-[a-zA-Z0-9_-]+\s+(v1\.[^\s]+)",
                body,
                re.IGNORECASE,
            )
            token_str = fallback_tok.group(1) if fallback_tok else None
        else:
            token_str = tok_match.group(1)

        return proposal_id, provided_hash, token_str

