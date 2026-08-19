"""
CloudPilot AI — Unified FastAPI Service Entry Point

Mounts REST API routes for all modules (M1 to M10):
- Discovery (M1)
- Cost Intelligence (M2)
- Application Intelligence (M3)
- Risk Intelligence (M4)
- Strategy Agent (M5)
- Digital Twin (M6)
- Explainability (M7)
- Learning Agent (M8)
- Decision Engine (M9)
- Autonomous Execution (M10)
"""

import logging
import os
import sys
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import route initializers
from discovery_routes import create_discovery_router
from cost_routes import init_routes as init_cost_routes
from application_routes import create_application_router
from risk_routes import create_risk_router
from strategy_routes import create_strategy_router
from simulation_routes import create_simulation_router
from explanation_routes import create_explanation_router
from learning_routes import create_learning_router
from decision_routes import create_decision_router
from execution_routes import create_execution_router

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from demo_routes import create_demo_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("cloudpilot")

# Initialize FastAPI app
app = FastAPI(
    title="CloudPilot AI Platform",
    description="Unified cloud reasoning and autonomous optimization engine",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> RedirectResponse:
    """Redirect root endpoint to the Command Center dashboard."""
    return RedirectResponse(url="/dashboard/")



def mount_all_routers() -> None:
    """Instantiate mock agents/repositories and register all routes."""
    logger.info("Initializing and mounting CloudPilot AI modules...")

    # Create mock/dummy components to ensure startup succeeds without active DB/cloud connections
    mock_repo = MagicMock()
    mock_agent = MagicMock()

    # M1 Discovery
    logger.info("Mounting Discovery Agent (M1) routes...")
    app.include_router(create_discovery_router(repository=mock_repo, agent=mock_agent))

    # M2 Cost
    logger.info("Mounting Cost Agent (M2) routes...")
    mock_access_control = MagicMock()
    app.include_router(init_cost_routes(mock_agent, mock_repo, mock_access_control))

    # M3 Application
    logger.info("Mounting Application Agent (M3) routes...")
    app.include_router(create_application_router(agent=mock_agent, repository=mock_repo))

    # M4 Risk
    logger.info("Mounting Risk Agent (M4) routes...")
    app.include_router(create_risk_router(agent=mock_agent, repository=mock_repo))

    # M5 Strategy
    logger.info("Mounting Strategy Agent (M5) routes...")
    app.include_router(create_strategy_router(agent=mock_agent, repository=mock_repo))

    # M6 Digital Twin
    logger.info("Mounting Digital Twin (M6) routes...")
    app.include_router(create_simulation_router(agent=mock_agent, repository=mock_repo))

    # M7 Explainability
    logger.info("Mounting Explainability Engine (M7) routes...")
    app.include_router(create_explanation_router(agent=mock_agent, repository=mock_repo))

    # M8 Learning
    logger.info("Mounting Learning Agent (M8) routes...")
    # Import concrete agent for concrete responses if possible
    try:
        from learning_agent import LearningAgent
        from learning_repository import LearningRepository
        concrete_learning_agent = LearningAgent()
        app.include_router(create_learning_router(agent=concrete_learning_agent, repository=mock_repo))
    except Exception:
        app.include_router(create_learning_router(agent=mock_agent, repository=mock_repo))

    # M9 Decision Engine
    logger.info("Mounting Decision Engine (M9) routes...")
    try:
        from decision_agent import DecisionAgent
        concrete_decision_agent = DecisionAgent()
        app.include_router(create_decision_router(agent=concrete_decision_agent, repository=mock_repo))
    except Exception:
        app.include_router(create_decision_router(agent=mock_agent, repository=mock_repo))

    # M10 Execution Agent
    logger.info("Mounting Execution Agent (M10) routes...")
    try:
        from execution_agent import ExecutionAgent
        concrete_exec_agent = ExecutionAgent()
        app.include_router(create_execution_router(agent=concrete_exec_agent, repository=mock_repo))
    except Exception:
        app.include_router(create_execution_router(agent=mock_agent, repository=mock_repo))

    # M11 Demo Router & Static files
    logger.info("Mounting Demo Engine (M11) routes...")
    app.include_router(create_demo_router())
    app.mount("/dashboard", StaticFiles(directory="static", html=True), name="static")

    logger.info("All modules mounted successfully!")


# Mount routers on startup
mount_all_routers()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
