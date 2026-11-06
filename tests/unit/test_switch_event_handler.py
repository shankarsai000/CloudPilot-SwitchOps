"""
Unit tests for SwitchEventHandler (Phase 4.2).

Validates:
- Wire protocol frame validation (SUPPORTED_FRAME_TYPES, payload dictionary requirement).
- Switch-to-CloudPilot identity boundary resolution (never trusts display names or caller roles).
- Role escalation rejection when unverified metadata is passed.
- Command parsing for proposal approval and rejection.
"""

import pytest

from app.domain.approvals import ApproverRole
from app.integrations.switch.event_handler import SwitchEventHandler
from app.integrations.switch.exceptions import SwitchProtocolError


def test_validate_frame_success():
    handler = SwitchEventHandler()

    valid_frame = {
        "type": "event",
        "event": "message",
        "payload": {
            "body": "@CloudPilot review",
            "sender": "@lead:switch",
        },
    }
    validated = handler.validate_frame(valid_frame)
    assert validated["type"] == "event"


def test_validate_frame_invalid_type():
    handler = SwitchEventHandler()

    with pytest.raises(SwitchProtocolError) as exc_info:
        handler.validate_frame({"type": "malformed_frame"})
    assert "Unsupported or missing Switch frame type" in str(exc_info.value)


def test_validate_frame_missing_payload_on_event():
    handler = SwitchEventHandler()

    with pytest.raises(SwitchProtocolError) as exc_info:
        handler.validate_frame({"type": "event"})
    assert "missing a valid 'payload' dictionary" in str(exc_info.value)


def test_resolve_principal_authoritative_directory():
    """Verify registered principals receive authoritative roles from server directory."""
    handler = SwitchEventHandler()

    # Known lead in directory without caller role claim
    principal = handler.resolve_authenticated_principal(
        sender="@platform-lead:switch",
        sender_name="Untrusted Name",
    )
    assert principal.authenticated is True
    assert principal.role == ApproverRole.PLATFORM_LEAD
    assert principal.principal_id == "@platform-lead:switch"

    # Conflicting role claim must be rejected as escalation/mismatch attempt
    mismatch = handler.resolve_authenticated_principal(
        sender="@platform-lead:switch",
        sender_name="Untrusted Name",
        metadata={"user_role": "OPERATOR"},
    )
    assert mismatch.authenticated is False
    assert mismatch.auth_mechanism == "ROLE_ESCALATION_REJECTED"


def test_resolve_principal_unregistered_fails_closed():
    """Verify unregistered senders are marked unauthenticated and assigned VIEWER role."""
    handler = SwitchEventHandler()

    principal = handler.resolve_authenticated_principal(
        sender="@unknown-intruder:switch",
        sender_name="Chief Executive Architect",  # Untrusted display name
        metadata={"user_role": "PLATFORM_LEAD"},    # Untrusted role claim
    )
    assert principal.authenticated is False
    assert principal.role == ApproverRole.VIEWER


def test_parse_approval_command_variants():
    """Verify robust parsing of approval commands."""
    cmd1 = "@cloudpilot-ops-agent approve proposal prop-92d2777974"
    res1 = SwitchEventHandler.parse_approval_command(cmd1)
    assert res1 is not None
    prop_id, p_hash, tok = res1
    assert prop_id == "prop-92d2777974"
    assert p_hash is None
    assert tok is None

    cmd2 = "@cloudpilot-ops-agent approve proposal prop-abcdef1234 hash 25e4cbf79bc553e2 token v1.tok123"
    res2 = SwitchEventHandler.parse_approval_command(cmd2)
    assert res2 is not None
    prop_id, p_hash, tok = res2
    assert prop_id == "prop-abcdef1234"
    assert p_hash == "25e4cbf79bc553e2"
    assert tok == "v1.tok123"

    cmd_non_approval = "@cloudpilot-ops-agent review staging infrastructure"
    assert SwitchEventHandler.parse_approval_command(cmd_non_approval) is None
