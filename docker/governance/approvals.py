"""
Approval Routing & Human-in-the-Loop Interruption Management.

Routes approvals based on risk, business criticality, blast radius, and policy.
Manages approval lifecycles, expirations, conflicts, and multi-party signoffs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
from typing import Dict, List, Optional, Tuple
import uuid

from governance.models import (
    ActionEvaluation,
    ActionRiskLevel,
    ApprovalDecisionRecord,
    ApprovalRequest,
    ApprovalRoute,
    ApprovalStatus,
    BusinessCriticality,
    ProposedAction,
    ReversibilityType,
)


class ApprovalRouter:
    """
    Intelligent approval workflow router and lifecycle engine.
    """

    def __init__(self, default_ttl_hours: int = 2) -> None:
        self.default_ttl_hours = default_ttl_hours
        self._requests: Dict[str, ApprovalRequest] = {}
        self._mutex = threading.Lock()

    def determine_route(
        self,
        action: ProposedAction,
        evaluation: ActionEvaluation,
    ) -> ApprovalRoute:
        """
        Determine the proper approval destination based on 9 evaluation factors.
        """
        # Blocked conditions
        if evaluation.is_blocked or not evaluation.policy_report.is_compliant:
            if any("PROD_DATABASE_PROTECTION" in v for v in evaluation.policy_report.policy_violations):
                return ApprovalRoute.BLOCKED
            if any("CHANGE_FREEZE" in v for v in evaluation.policy_report.policy_violations):
                return ApprovalRoute.BLOCKED

        # Irreversible actions in production require Executive signoff
        is_prod = action.environment.lower() in ("prod", "production") or evaluation.business_criticality == BusinessCriticality.TIER_1_MISSION_CRITICAL
        if is_prod and evaluation.reversibility == ReversibilityType.IRREVERSIBLE:
            return ApprovalRoute.EXECUTIVE_APPROVAL

        # Executive approval for Tier-1 or high cost impact (> $2,500/mo) or critical risk
        if (
            evaluation.business_criticality == BusinessCriticality.TIER_1_MISSION_CRITICAL
            or evaluation.risk_level in (ActionRiskLevel.HIGH, ActionRiskLevel.CRITICAL)
            or abs(action.estimated_cost_impact_usd) > 2500.0
        ):
            return ApprovalRoute.EXECUTIVE_APPROVAL

        # Security team approval for security group or network modifications
        if "sg" in action.action_type.lower() or "firewall" in action.action_type.lower() or "ingress" in action.action_type.lower():
            return ApprovalRoute.SECURITY_TEAM

        # SRE Team approval for production modifications or Tier-2 services
        if is_prod or evaluation.business_criticality == BusinessCriticality.TIER_2_IMPORTANT:
            return ApprovalRoute.SRE_TEAM

        # Engineering lead for reversible dev/staging changes with moderate risk
        if evaluation.risk_level == ActionRiskLevel.MEDIUM or evaluation.dependent_services_count > 1:
            return ApprovalRoute.ENGINEERING_LEAD

        # Non-production low risk reversible actions can auto-execute if autonomy allows
        if evaluation.reversibility == ReversibilityType.REVERSIBLE and evaluation.risk_level in (ActionRiskLevel.SAFE, ActionRiskLevel.LOW):
            return ApprovalRoute.AUTO_EXECUTE

        return ApprovalRoute.ENGINEERING_LEAD

    def create_approval_request(
        self,
        action: ProposedAction,
        evaluation: ActionEvaluation,
        route: Optional[ApprovalRoute] = None,
        ttl_hours: Optional[int] = None,
    ) -> ApprovalRequest:
        """Create and register a tracked approval request."""
        assigned_route = route or self.determine_route(action, evaluation)
        now = datetime.now(timezone.utc)
        ttl = ttl_hours or self.default_ttl_hours
        expires_at = now + timedelta(hours=ttl)

        request = ApprovalRequest(
            request_id=f"apr-{uuid.uuid4().hex[:8]}",
            action=action,
            evaluation=evaluation,
            required_route=assigned_route,
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
        )

        with self._mutex:
            self._requests[request.request_id] = request
        return request

    def submit_decision(
        self,
        request_id: str,
        approver: str,
        role: str,
        approved: bool,
        reason: Optional[str] = None,
    ) -> Tuple[bool, ApprovalRequest, str]:
        """
        Submit an approval or rejection decision.
        Handles expirations, conflict detection, and status updates.
        Returns (success, request, message).
        """
        now = datetime.now(timezone.utc)
        with self._mutex:
            request = self._requests.get(request_id)
            if not request:
                return False, None, f"Request '{request_id}' not found"

            # Check if expired
            if request.expires_at <= now:
                request.status = ApprovalStatus.EXPIRED
                return False, request, f"Approval request '{request_id}' has EXPIRED"

            if request.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED):
                return False, request, f"Approval request '{request_id}' is already finalized ({request.status.value})"

            # Record decision
            decision_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            record = ApprovalDecisionRecord(
                decision_id=f"dec-{uuid.uuid4().hex[:8]}",
                approver=approver,
                role=role,
                status=decision_status,
                reason=reason,
                decided_at=now,
            )
            request.decisions.append(record)

            # Conflict check: if one approver approved and another rejected
            decisions_statuses = set(d.status for d in request.decisions)
            if ApprovalStatus.APPROVED in decisions_statuses and ApprovalStatus.REJECTED in decisions_statuses:
                request.status = ApprovalStatus.CONFLICTED
                return False, request, f"Conflicting decisions detected for request '{request_id}' — marked CONFLICTED"

            if approved:
                request.status = ApprovalStatus.APPROVED
                request.finalized_at = now
                return True, request, f"Approval granted by {approver} ({role})"
            else:
                request.status = ApprovalStatus.REJECTED
                request.finalized_at = now
                return True, request, f"Approval rejected by {approver} ({role}): {reason}"

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        now = datetime.now(timezone.utc)
        with self._mutex:
            req = self._requests.get(request_id)
            if req and req.status == ApprovalStatus.PENDING and req.expires_at <= now:
                req.status = ApprovalStatus.EXPIRED
            return req

    def list_requests(
        self,
        status: Optional[ApprovalStatus] = None,
        route: Optional[ApprovalRoute] = None,
    ) -> List[ApprovalRequest]:
        now = datetime.now(timezone.utc)
        with self._mutex:
            results = []
            for req in self._requests.values():
                if req.status == ApprovalStatus.PENDING and req.expires_at <= now:
                    req.status = ApprovalStatus.EXPIRED
                if status and req.status != status:
                    continue
                if route and req.required_route != route:
                    continue
                results.append(req)
            return sorted(results, key=lambda r: r.created_at, reverse=True)

    def clear_all(self) -> None:
        with self._mutex:
            self._requests.clear()


_approval_router_instance: Optional[ApprovalRouter] = None


def get_approval_router() -> ApprovalRouter:
    global _approval_router_instance
    if _approval_router_instance is None:
        _approval_router_instance = ApprovalRouter()
    return _approval_router_instance
