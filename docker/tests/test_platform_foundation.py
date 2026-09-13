"""
Comprehensive automated tests for CloudPilot AI Platform Foundation (Phase 1).
Tests configuration, structured logging, error handling, database, Redis,
auth, RBAC, health/readiness, metrics, event architecture, base agents, and API v1.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.orm import Session

from core.api.v1.router import create_v1_router
from core.auth.dependencies import AuthenticatedUser, get_current_user, require_permission, require_role
from core.auth.rbac import Permission, Role, has_permission
from core.auth.security import create_access_token, decode_access_token, hash_password, verify_password
from core.config import Environment, Settings, get_settings
from core.database.base import Base
from core.database.connection import check_database_health, get_db, get_engine, get_session_factory
from core.errors import (
    AuthenticationError,
    AuthorizationError,
    CloudPilotError,
    ConflictError,
    ExternalProviderError,
    NotFoundError,
    ValidationError,
    register_error_handlers,
)
from core.events.bus import EventBus
from core.events.models import BaseEvent, EventType
from core.interfaces.adapters import BaseCloudAdapter, ProviderAdapterRegistry
from core.interfaces.agent import AgentExecutionResult, AgentMetadata, AgentStatus, BaseAgent
from core.logging import (
    ConsoleFormatter,
    CorrelationIdMiddleware,
    JSONLogFormatter,
    correlation_id_ctx,
    get_correlation_id,
    set_correlation_id,
)
from core.observability.health import get_health_status, get_readiness_status
from core.observability.metrics import MetricsCollector
from core.redis.client import InMemoryRedisFallback, check_redis_health, idempotency_lock
from core.service.repository import BaseRepository
from core.service.service import BaseService


# ══════════════════════════════════════════════════════════════════
# 1. Configuration Management Tests
# ══════════════════════════════════════════════════════════════════

class TestConfigurationManagement:
    """Validate settings loading, typing, and environment separation."""

    def test_default_settings_loaded(self) -> None:
        settings = get_settings()
        assert settings.app_name == "CloudPilot AI Platform"
        assert settings.app_version == "1.0.0"
        assert settings.is_testing is True

    def test_environment_parsing(self) -> None:
        prod_settings = Settings(environment="production")
        assert prod_settings.is_production is True
        assert prod_settings.is_development is False

        dev_settings = Settings(environment="development")
        assert dev_settings.is_development is True

    def test_secret_string_protection(self) -> None:
        settings = Settings()
        assert "SecretStr" in repr(settings.jwt_secret_key)
        assert settings.get_jwt_secret() is not None


# ══════════════════════════════════════════════════════════════════
# 2. Structured Logging & Correlation ID Tests
# ══════════════════════════════════════════════════════════════════

class TestStructuredLogging:
    """Validate JSON formatting and correlation context."""

    def test_json_log_formatter(self) -> None:
        formatter = JSONLogFormatter()
        set_correlation_id("req-test-12345")
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=50,
            msg="Discovery started for AWS",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        data = json.loads(formatted)
        assert data["level"] == "INFO"
        assert data["logger"] == "test_logger"
        assert data["message"] == "Discovery started for AWS"
        assert data["correlation_id"] == "req-test-12345"
        assert "timestamp" in data

    def test_console_log_formatter(self) -> None:
        formatter = ConsoleFormatter()
        set_correlation_id("req-console-999")
        record = logging.LogRecord(
            name="console_logger",
            level=logging.WARNING,
            pathname=__file__,
            lineno=60,
            msg="Cost spike detected",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "WARNING" in output
        assert "Cost spike detected" in output
        assert "req-console-999" in output


# ══════════════════════════════════════════════════════════════════
# 3. Centralized Error Handling Tests
# ══════════════════════════════════════════════════════════════════

class TestCentralizedErrorHandling:
    """Validate exception hierarchy and standard error responses."""

    def test_exception_properties(self) -> None:
        err = NotFoundError("Resource not found", details={"id": "res-999"})
        assert err.status_code == 404
        assert err.code == "RESOURCE_NOT_FOUND"
        assert err.details["id"] == "res-999"

        prov_err = ExternalProviderError("aws", "Throttled")
        assert prov_err.status_code == 502
        assert prov_err.code == "EXTERNAL_PROVIDER_FAILURE"

    def test_error_handlers_with_test_app(self) -> None:
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/trigger-not-found")
        def route_not_found():
            raise NotFoundError("Resource 'ec2-1' was deleted")

        @app.get("/trigger-unhandled")
        def route_unhandled():
            raise ValueError("Unexpected division by zero")

        client = TestClient(app, raise_server_exceptions=False)

        resp404 = client.get("/trigger-not-found")
        assert resp404.status_code == 404
        payload = resp404.json()
        assert payload["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert "ec2-1" in payload["error"]["message"]
        assert "request_id" in payload["error"]

        resp500 = client.get("/trigger-unhandled")
        assert resp500.status_code == 500
        payload500 = resp500.json()
        assert payload500["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ══════════════════════════════════════════════════════════════════
# 4. Database Connectivity & Session Management Tests
# ══════════════════════════════════════════════════════════════════

class TestDatabaseLayer:
    """Validate database engine, sessions, and health checks."""

    def test_database_health_check(self) -> None:
        status = check_database_health()
        assert status.connected is True
        assert status.latency_ms is not None
        assert status.latency_ms >= 0.0

    def test_get_db_session_lifecycle(self) -> None:
        gen = get_db()
        session = next(gen)
        assert isinstance(session, Session)
        try:
            next(gen)
        except StopIteration:
            pass  # Expected end of generator


# ══════════════════════════════════════════════════════════════════
# 5. Redis Integration & Fallback Tests
# ══════════════════════════════════════════════════════════════════

class TestRedisLayer:
    """Validate Redis fallback, caching operations, and idempotency locks."""

    def test_in_memory_redis_crud(self) -> None:
        client = InMemoryRedisFallback()
        assert client.ping() is True

        client.set("key1", "value1")
        assert client.get("key1") == "value1"
        assert client.exists("key1") == 1

        client.delete("key1")
        assert client.get("key1") is None

    def test_idempotency_lock(self) -> None:
        with idempotency_lock("test-action-123", ttl_seconds=10) as acquired1:
            assert acquired1 is True
            # Concurrent attempt should be blocked
            with idempotency_lock("test-action-123", ttl_seconds=10) as acquired2:
                assert acquired2 is False

        # Once released, can acquire again
        with idempotency_lock("test-action-123", ttl_seconds=10) as acquired3:
            assert acquired3 is True

    def test_redis_health_check(self) -> None:
        health = check_redis_health()
        assert health.connected is True
        assert health.latency_ms is not None


# ══════════════════════════════════════════════════════════════════
# 6. Authentication & RBAC Tests
# ══════════════════════════════════════════════════════════════════

class TestAuthAndRBAC:
    """Validate password hashing, JWT tokens, and RBAC matrix."""

    def test_password_hashing_and_verification(self) -> None:
        hashed = hash_password("SuperSecureSecret123!")
        assert verify_password("SuperSecureSecret123!", hashed) is True
        assert verify_password("WrongPassword", hashed) is False

    def test_jwt_token_roundtrip(self) -> None:
        token = create_access_token(
            subject="usr-100",
            username="alice",
            role="operator",
            permissions=["discovery:read", "execution:run"],
        )
        payload = decode_access_token(token)
        assert payload.sub == "usr-100"
        assert payload.username == "alice"
        assert payload.role == "operator"
        assert "execution:run" in payload.permissions

    def test_rbac_permission_evaluation(self) -> None:
        # Admin has wildcard access
        assert has_permission("admin", [], Permission.EXECUTION_RUN.value) is True
        assert has_permission("admin", [], "any:custom:perm") is True

        # Operator can run executions
        assert has_permission("operator", [], Permission.EXECUTION_RUN.value) is True

        # Viewer cannot run executions
        assert has_permission("viewer", [], Permission.EXECUTION_RUN.value) is False
        assert has_permission("viewer", [], Permission.DISCOVERY_READ.value) is True

        # Explicit user permissions override role restrictions
        assert has_permission("viewer", ["execution:run"], Permission.EXECUTION_RUN.value) is True


# ══════════════════════════════════════════════════════════════════
# 7. Health, Readiness & Metrics Tests
# ══════════════════════════════════════════════════════════════════

class TestObservabilityProbes:
    """Validate liveness, readiness, and Prometheus metrics."""

    def test_health_report(self) -> None:
        report = get_health_status()
        assert report.status == "healthy"
        assert report.version == "1.0.0"
        assert report.uptime_seconds >= 0

    def test_readiness_report(self) -> None:
        report = get_readiness_status()
        assert report.status == "ready"
        assert report.database.connected is True
        assert report.redis.connected is True
        assert "M1_discovery" in report.modules

    def test_metrics_collection_and_rendering(self) -> None:
        collector = MetricsCollector()
        collector.record_http_request("GET", "/api/v1/health", 200, 0.015)
        collector.record_agent_execution("M1", "success")
        collector.record_error("RESOURCE_NOT_FOUND")

        rendered = collector.render_prometheus()
        assert "http_requests_total" in rendered
        assert 'agent="M1"' in rendered
        assert 'code="RESOURCE_NOT_FOUND"' in rendered

        summary = collector.get_summary()
        assert summary["total_http_requests"] == 1
        assert summary["total_errors"] == 1


# ══════════════════════════════════════════════════════════════════
# 8. Event Architecture Tests
# ══════════════════════════════════════════════════════════════════

class TestEventArchitecture:
    """Validate async event bus publish/subscribe."""

    @pytest.mark.asyncio
    async def test_event_bus_pub_sub(self) -> None:
        bus = EventBus()
        received = []

        def handler(event: BaseEvent) -> None:
            received.append(event)

        bus.subscribe(EventType.RESOURCE_DISCOVERED.value, handler)

        event = BaseEvent(
            event_type=EventType.RESOURCE_DISCOVERED.value,
            source_module="M1",
            payload={"resource_id": "i-12345", "type": "ec2_instance"},
        )
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].payload["resource_id"] == "i-12345"

    @pytest.mark.asyncio
    async def test_wildcard_event_subscription(self) -> None:
        bus = EventBus()
        all_events = []

        bus.subscribe("*", lambda e: all_events.append(e))

        await bus.publish(BaseEvent(event_type="event.one", source_module="test"))
        await bus.publish(BaseEvent(event_type="event.two", source_module="test"))

        assert len(all_events) == 2


# ══════════════════════════════════════════════════════════════════
# 9. Agent Base Interfaces & Adapter Registry Tests
# ══════════════════════════════════════════════════════════════════

class MockDummyAgent(BaseAgent):
    """Concrete test implementation of BaseAgent."""

    def _execute(self, context: dict) -> AgentExecutionResult:
        if context.get("fail"):
            raise RuntimeError("Simulation failure")
        return AgentExecutionResult(success=True, data={"processed": True})


class TestAgentInterfaces:
    """Validate agent lifecycle and adapter registry."""

    def test_base_agent_lifecycle(self) -> None:
        metadata = AgentMetadata(
            module_id="M99",
            name="Dummy Test Agent",
            capabilities=["test_run"],
        )
        agent = MockDummyAgent(metadata)
        assert agent.status == AgentStatus.IDLE

        agent.initialize()
        assert agent.status == AgentStatus.READY

        res = agent.run({"param": 1})
        assert res.success is True
        assert res.execution_time_ms >= 0.0

        # Failure handling
        fail_res = agent.run({"fail": True})
        assert fail_res.success is False
        assert "Simulation failure" in fail_res.message
        assert agent.status == AgentStatus.ERROR

        agent.shutdown()
        assert agent.status == AgentStatus.IDLE

    def test_provider_adapter_registry(self) -> None:
        registry = ProviderAdapterRegistry()

        class MockAWSCloudAdapter(BaseCloudAdapter):
            def discover(self):
                return ([], [])
            def health_check(self):
                return True

        registry.register_cloud_adapter("aws", MockAWSCloudAdapter)
        retrieved = registry.get_cloud_adapter("AWS")  # case insensitive
        assert retrieved is MockAWSCloudAdapter


# ══════════════════════════════════════════════════════════════════
# 10. Repository & Service Pattern Tests
# ══════════════════════════════════════════════════════════════════

class SampleItem(Base):
    """Sample table for testing generic BaseRepository."""
    __tablename__ = "test_sample_items"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)


class TestRepositoryAndServicePattern:
    """Validate generic BaseRepository and BaseService with SQLite."""

    @pytest.fixture(autouse=True)
    def setup_sample_table(self) -> None:
        engine = get_engine()
        Base.metadata.create_all(bind=engine, tables=[SampleItem.__table__])
        yield
        Base.metadata.drop_all(bind=engine, tables=[SampleItem.__table__])

    def test_repository_crud(self) -> None:
        factory = get_session_factory()
        with factory() as session:
            repo = BaseRepository(SampleItem, session)
            item = repo.create(SampleItem(id=1, name="Item Alpha"))
            session.commit()

            fetched = repo.get_by_id(1)
            assert fetched is not None
            assert fetched.name == "Item Alpha"

            assert repo.count() == 1

            repo.delete(1)
            session.commit()
            assert repo.get_by_id(1) is None


# ══════════════════════════════════════════════════════════════════
# 11. Full API v1 Integration Tests
# ══════════════════════════════════════════════════════════════════

class TestFullAPIIntegration:
    """Validate FastAPI integration with versioning, auth, probes, and metrics."""

    @pytest.fixture
    def test_client(self) -> TestClient:
        import main
        return TestClient(main.app)

    def test_liveness_probe_endpoint(self, test_client: TestClient) -> None:
        resp = test_client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"

    def test_readiness_probe_endpoint(self, test_client: TestClient) -> None:
        resp = test_client.get("/readyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"

    def test_metrics_endpoint(self, test_client: TestClient) -> None:
        resp = test_client.get("/metrics")
        assert resp.status_code == 200
        assert "http_requests_total" in resp.text

    def test_api_v1_health(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_api_v1_auth_token_and_me(self, test_client: TestClient) -> None:
        login_resp = test_client.post(
            "/api/v1/auth/token",
            json={"username": "bob", "password": "secure-password", "role": "operator"},
        )
        assert login_resp.status_code == 200
        token_data = login_resp.json()
        token = token_data["access_token"]
        assert token_data["role"] == "operator"

        # Call /me endpoint with Bearer token
        me_resp = test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["username"] == "bob"
        assert me_data["role"] == "operator"

    def test_legacy_health_endpoints_backward_compatibility(self, test_client: TestClient) -> None:
        # Legacy Discovery health endpoint
        disc_resp = test_client.get("/api/discovery/health")
        assert disc_resp.status_code == 200

        # Legacy Demo health endpoint
        demo_resp = test_client.get("/api/demo/health")
        assert demo_resp.status_code == 200
