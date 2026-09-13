"""
Master API v1 Router aggregating all core platform and module sub-routers.
"""

import logging
from typing import Any, Optional
from fastapi import APIRouter

from core.api.v1.auth_routes import auth_router
from core.api.v1.health_routes import health_router

logger = logging.getLogger("cloudpilot.api.v1")


def create_v1_router(
    discovery_router: Optional[APIRouter] = None,
    cost_router: Optional[APIRouter] = None,
    application_router: Optional[APIRouter] = None,
    risk_router: Optional[APIRouter] = None,
    strategy_router: Optional[APIRouter] = None,
    simulation_router: Optional[APIRouter] = None,
    explanation_router: Optional[APIRouter] = None,
    learning_router: Optional[APIRouter] = None,
    decision_router: Optional[APIRouter] = None,
    execution_router: Optional[APIRouter] = None,
    demo_router: Optional[APIRouter] = None,
) -> APIRouter:
    """
    Construct the aggregated /api/v1 master router.
    Mounts core foundation routes (auth, health, metrics) and all module endpoints.
    """
    v1_router = APIRouter(prefix="/api/v1")

    # Core Foundation routes
    v1_router.include_router(health_router)
    v1_router.include_router(auth_router)

    # Mount module routers under v1 if supplied
    if discovery_router:
        v1_router.include_router(discovery_router)
    if cost_router:
        v1_router.include_router(cost_router)
    if application_router:
        v1_router.include_router(application_router)
    if risk_router:
        v1_router.include_router(risk_router)
    if strategy_router:
        v1_router.include_router(strategy_router)
    if simulation_router:
        v1_router.include_router(simulation_router)
    if explanation_router:
        v1_router.include_router(explanation_router)
    if learning_router:
        v1_router.include_router(learning_router)
    if decision_router:
        v1_router.include_router(decision_router)
    if execution_router:
        v1_router.include_router(execution_router)
    if demo_router:
        v1_router.include_router(demo_router)

    # Mount digital enterprise simulator router
    try:
        from simulator.routes import simulator_router
        v1_router.include_router(simulator_router)
    except Exception as exc:
        logger.warning("Could not mount simulator router: %s", exc)

    # Mount intelligence pipeline router
    try:
        from pipeline.routes import pipeline_router
        v1_router.include_router(pipeline_router)
    except Exception as exc:
        logger.warning("Could not mount pipeline router: %s", exc)

    # Mount TrueForge autonomous agent runtime router
    try:
        from trueforge.routes import router as trueforge_router
        v1_router.include_router(trueforge_router, prefix="/agents")
    except Exception as exc:
        logger.warning("Could not mount trueforge router: %s", exc)

    # Mount Safety & Autonomy Governance router
    try:
        from governance.routes import router as governance_router
        v1_router.include_router(governance_router, prefix="/governance")
    except Exception as exc:
        logger.warning("Could not mount governance router: %s", exc)

    # Mount Outcome Verification & Learning Loop router
    try:
        from verification.routes import router as verification_router
        v1_router.include_router(verification_router)
    except Exception as exc:
        logger.warning("Could not mount verification router: %s", exc)

    # Mount Command Center router
    try:
        from core.api.v1.command_center_routes import router as command_center_router
        v1_router.include_router(command_center_router)
    except Exception as exc:
        logger.warning("Could not mount command center router: %s", exc)

    # Mount Production Multi-Cloud Providers router
    try:
        from providers.routes import router as providers_router
        v1_router.include_router(providers_router)
    except Exception as exc:
        logger.warning("Could not mount providers router: %s", exc)

    logger.info("Assembled API v1 router with core and module routes")
    return v1_router
