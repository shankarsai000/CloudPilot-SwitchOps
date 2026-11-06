#!/usr/bin/env python3
"""
CloudPilot SwitchOps — Standard Hackathon Submission Demonstration Script (Offline Emulated)

NOTE: This script executes the verified OFFLINE EMULATED workflow using EmulatedSwitchBridge.
For strict live external Switch operations, run: python scripts/demo_submission_live.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from scripts.demo_submission_offline import run_offline_demo

if __name__ == "__main__":
    sys.exit(asyncio.run(run_offline_demo()))
