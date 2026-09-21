"""
Production configuration management for CloudPilot AI Platform.

Enforces environment separation, strong typing with Pydantic Settings,
and safe secret handling with SecretStr.
"""

from enum import Enum
from functools import lru_cache
from typing import List, Optional
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application runtime environments."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """
    Unified platform settings with validation and environment loading.
    Loaded hierarchically from environment variables, .env, and defaults.
    """
    # Application metadata
    app_name: str = Field(default="CloudPilot AI Platform", description="Application display name")
    app_version: str = Field(default="1.0.0", description="Semver application version")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment (development, testing, staging, production)",
    )
    debug: bool = Field(default=False, description="Enable debug mode")

    # Networking & Server
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server listen port")
    workers: int = Field(default=1, description="Uvicorn/Gunicorn worker count")
    cors_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins list",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="json",
        description="Log output format ('json' for structured, 'console' for human-readable)",
    )

    # Security & Auth
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("insecure-dev-secret-key-change-in-production-min-32-chars!"),
        description="Secret key for signing JWT tokens",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiration_minutes: int = Field(default=1440, description="JWT token validity duration in minutes (default 24h)")
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="Static platform API key for automation/service-to-service access",
    )

    # Database (PostgreSQL)
    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/cloudpilot",
        description="PostgreSQL SQLAlchemy connection string",
    )
    db_pool_size: int = Field(default=10, description="SQLAlchemy connection pool size")
    db_max_overflow: int = Field(default=5, description="Maximum overflow connections in pool")
    db_pool_timeout: int = Field(default=30, description="Connection pool checkout timeout in seconds")
    db_pool_recycle: int = Field(default=1800, description="Connection pool recycle period in seconds")

    # Cache & Queues (Redis)
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_max_connections: int = Field(default=20, description="Maximum Redis connection pool size")
    redis_default_ttl: int = Field(default=3600, description="Default cache expiration in seconds")

    # Prometheus / Metrics
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection and /metrics endpoint")

    # AWS Cloud Integration (Read-Only Least Privilege)
    aws_region: str = Field(default="ap-south-1", description="Target AWS region (e.g. ap-south-1)")
    aws_role_arn: Optional[str] = Field(
        default=None,
        description="Dedicated CloudPilotReadOnlyRole ARN for STS AssumeRole",
    )
    aws_external_id: Optional[str] = Field(
        default=None,
        description="External ID for IAM AssumeRole trust policy enforcement",
    )
    aws_access_key_id: Optional[SecretStr] = Field(
        default=None,
        description="Static or bootstrap AWS Access Key ID",
    )
    aws_secret_access_key: Optional[SecretStr] = Field(
        default=None,
        description="Static or bootstrap AWS Secret Access Key",
    )
    aws_session_token: Optional[SecretStr] = Field(
        default=None,
        description="Optional AWS Session Token for temporary credentials",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("environment", mode="before")
    @classmethod
    def parse_environment(cls, value: str) -> Environment:
        """Coerce strings to Environment enum case-insensitively."""
        if isinstance(value, str):
            norm = value.strip().lower()
            if norm in ("test", "testing"):
                return Environment.TESTING
            if norm in ("prod", "production"):
                return Environment.PRODUCTION
            if norm in ("stage", "staging"):
                return Environment.STAGING
            return Environment.DEVELOPMENT
        return value

    @property
    def is_production(self) -> bool:
        """Check whether running in production."""
        return self.environment == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        """Check whether running under test runner."""
        return self.environment == Environment.TESTING

    @property
    def is_development(self) -> bool:
        """Check whether running in local development."""
        return self.environment == Environment.DEVELOPMENT

    def get_jwt_secret(self) -> str:
        """Retrieve plain JWT secret string safely."""
        return self.jwt_secret_key.get_secret_value()

    @property
    def has_live_aws_credentials(self) -> bool:
        """Check whether real AWS credentials or IAM role ARN are configured."""
        return bool(self.aws_role_arn or (self.aws_access_key_id and self.aws_secret_access_key))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton instance of validated settings."""
    return Settings()
