"""
Rollout Manager Component

Manages progressive rollout deployment strategies: Canary (10% -> 25% -> 50% -> 100%),
Blue/Green switches, Rolling Updates, and Shadow deployments.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from models_execution import RolloutProgress, RolloutStrategy

logger = logging.getLogger(__name__)

CANARY_STEPS = [10.0, 25.0, 50.0, 100.0]


class RolloutManager:
    """Manages progression steps for progressive rollouts."""

    def __init__(self) -> None:
        """Initialize Rollout Manager."""
        pass

    def initialize_rollout(self, strategy: RolloutStrategy) -> RolloutProgress:
        """Initialize a new rollout tracker.

        Args:
            strategy: RolloutStrategy enum

        Returns:
            RolloutProgress tracker initialized
        """
        active_slice = "primary"
        if strategy == RolloutStrategy.BLUE_GREEN:
            active_slice = "blue"
        elif strategy == RolloutStrategy.CANARY:
            active_slice = "canary"

        initial_percent = 0.0
        if strategy == RolloutStrategy.DIRECT:
            initial_percent = 100.0

        return RolloutProgress(
            strategy=strategy,
            target_percentage=100.0,
            current_percentage=initial_percent,
            active_slice=active_slice,
            step_index=0,
            last_updated=datetime.utcnow(),
        )

    def advance_rollout(self, rollout: RolloutProgress) -> tuple[RolloutProgress, bool]:
        """Advance the rollout to the next phase/percentage.

        Args:
            rollout: Active RolloutProgress tracker

        Returns:
            Tuple of (updated RolloutProgress, is_finished)
        """
        strategy = rollout.strategy
        is_finished = False

        if strategy == RolloutStrategy.DIRECT:
            rollout.current_percentage = 100.0
            is_finished = True
        elif strategy == RolloutStrategy.CANARY:
            idx = rollout.step_index
            if idx < len(CANARY_STEPS):
                rollout.current_percentage = CANARY_STEPS[idx]
                rollout.step_index += 1
                if rollout.current_percentage >= 100.0:
                    is_finished = True
            else:
                is_finished = True
        elif strategy == RolloutStrategy.BLUE_GREEN:
            if rollout.active_slice == "blue":
                rollout.active_slice = "green"
                rollout.current_percentage = 100.0
                is_finished = True
            else:
                rollout.active_slice = "blue"
                rollout.current_percentage = 100.0
                is_finished = True
        elif strategy == RolloutStrategy.ROLLING:
            # Multi-step increments of 25%
            next_pct = rollout.current_percentage + 25.0
            if next_pct >= 100.0:
                rollout.current_percentage = 100.0
                is_finished = True
            else:
                rollout.current_percentage = next_pct
        else:
            # Shadow
            rollout.current_percentage = 100.0
            is_finished = True

        rollout.last_updated = datetime.utcnow()
        logger.info(
            "Rollout advanced (%s): %s%% (%s slice)",
            strategy.value, rollout.current_percentage, rollout.active_slice
        )
        return rollout, is_finished
