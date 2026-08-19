"""
Cost Intelligence Service - FastAPI Application Entry Point
"""

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cost_agent import CostIntelligenceAgent
from cost_repository import CostRepository
from cost_access_control import CostAccessControl
from cost_routes import init_routes

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Cost Intelligence Agent",
    description="CloudPilot AI Cost Intelligence Agent (M2-CIA)",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
def _init_components() -> None:
    """Initialize cost intelligence components."""
    logger.info("Initializing Cost Intelligence Agent...")
    
    # Database
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost/costs")
    repository = CostRepository(db_url)
    
    # Cloud providers config
    aws_config = None
    if os.getenv("AWS_REGION"):
        aws_config = {
            "region": os.getenv("AWS_REGION", "us-east-1"),
            "profile_name": os.getenv("AWS_PROFILE")
        }
    
    azure_config = None
    if os.getenv("AZURE_SUBSCRIPTION_ID"):
        azure_config = {
            "subscription_id": os.getenv("AZURE_SUBSCRIPTION_ID"),
            "tenant_id": os.getenv("AZURE_TENANT_ID")
        }
    
    gcp_config = None
    if os.getenv("GCP_PROJECT_ID"):
        gcp_config = {
            "project_id": os.getenv("GCP_PROJECT_ID"),
            "dataset_id": os.getenv("GCP_DATASET_ID", "billing_export")
        }
    
    # Cost agent
    agent = CostIntelligenceAgent(
        aws_config=aws_config,
        azure_config=azure_config,
        gcp_config=gcp_config
    )
    
    # Access control
    access_control = CostAccessControl()
    
    # Initialize routes
    router = init_routes(agent, repository, access_control)
    app.include_router(router)
    
    logger.info("Cost Intelligence Agent initialized successfully")


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize on startup."""
    _init_components()


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Cost Intelligence Agent",
        "version": "1.0.0"
    }


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "service": "Cost Intelligence Agent (M2-CIA)",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "operational"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
