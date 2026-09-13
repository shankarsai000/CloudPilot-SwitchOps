"""
Emergency Stop (Kill Switch) Mechanism.

Provides immediate, fail-safe halting of all or scoped autonomous operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Dict, List, Optional

from governance.models import EmergencyStopState


class EmergencyStopManager:
    """
    Thread-safe emergency stop governor.
    Supports both global kill-switches and fine-grained scoped halts
    (e.g., stopping all production actions while allowing dev testing).
    """

    def __init__(self) -> None:
        # Keyed by scope: "global", "env:prod", "service:payment", etc.
        self._stops: Dict[str, EmergencyStopState] = {}
        self._mutex = threading.Lock()

    def engage(
        self,
        scope: str = "global",
        reason: str = "Operator engaged emergency stop",
        activated_by: str = "operator",
    ) -> EmergencyStopState:
        """
        Engage an emergency stop on a scope or globally.
        Immediately halts authorization and execution of matching operations.
        """
        normalized_scope = scope.strip().lower()
        now = datetime.now(timezone.utc)
        state = EmergencyStopState(
            is_active=True,
            scope=normalized_scope,
            reason=reason,
            activated_by=activated_by,
            activated_at=now,
        )
        with self._mutex:
            self._stops[normalized_scope] = state
        return state

    def release(self, scope: str = "global") -> bool:
        """
        Disengage an emergency stop for a given scope.
        Returns True if a stop was found and released, False otherwise.
        """
        normalized_scope = scope.strip().lower()
        with self._mutex:
            if normalized_scope in self._stops:
                del self._stops[normalized_scope]
                return True
            return False

    def is_stopped(
        self,
        environment: Optional[str] = None,
        service: Optional[str] = None,
    ) -> bool:
        """
        Check if an operation is blocked by an active emergency stop.
        Checks global stop, environment-level stop, and service-level stop.
        """
        with self._mutex:
            # 1. Global stop
            if "global" in self._stops:
                return True

            # 2. Environment stop (e.g. "env:prod", "env:production")
            if environment:
                env_clean = environment.strip().lower()
                if f"env:{env_clean}" in self._stops:
                    return True
                if env_clean in ("prod", "production") and ("env:prod" in self._stops or "env:production" in self._stops):
                    return True

            # 3. Service stop (e.g. "service:PaymentService")
            if service:
                svc_clean = service.strip().lower()
                if f"service:{svc_clean}" in self._stops:
                    return True

            return False

    def get_stop_reason(
        self,
        environment: Optional[str] = None,
        service: Optional[str] = None,
    ) -> Optional[str]:
        """Get the active stop reason affecting the given environment or service."""
        with self._mutex:
            if "global" in self._stops:
                return f"GLOBAL EMERGENCY STOP: {self._stops['global'].reason}"

            if environment:
                env_clean = environment.strip().lower()
                for key in (f"env:{env_clean}", "env:prod" if env_clean in ("prod", "production") else ""):
                    if key and key in self._stops:
                        return f"ENVIRONMENT EMERGENCY STOP ({environment}): {self._stops[key].reason}"

            if service:
                svc_clean = service.strip().lower()
                if f"service:{svc_clean}" in self._stops:
                    return f"SERVICE EMERGENCY STOP ({service}): {self._stops[f'service:{svc_clean}'].reason}"

            return None

    def list_active_stops(self) -> List[EmergencyStopState]:
        """Return all active emergency stops."""
        with self._mutex:
            return list(self._stops.values())

    def reset_all(self) -> None:
        """Clear all active emergency stops."""
        with self._mutex:
            self._stops.clear()


_emergency_stop_instance: Optional[EmergencyStopManager] = None


def get_emergency_stop_manager() -> EmergencyStopManager:
    global _emergency_stop_instance
    if _emergency_stop_instance is None:
        _emergency_stop_instance = EmergencyStopManager()
    return _emergency_stop_instance
