"""
Global test configuration and fixtures for CloudPilot AI test suite.
"""

import os
import sys
from pathlib import Path
import pytest

# Ensure docker directory is on sys.path
docker_dir = Path(__file__).resolve().parent
if str(docker_dir) not in sys.path:
    sys.path.insert(0, str(docker_dir))

# Set test environment flags
os.environ["ENVIRONMENT"] = "testing"
os.environ["CLOUD_ENV"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-unit-testing-min-32-chars!!"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"


@pytest.fixture(autouse=True)
def set_testing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure testing environment variables are active for every test."""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("CLOUD_ENV", "testing")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-unit-testing-min-32-chars!!")
