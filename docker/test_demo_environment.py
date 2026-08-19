"""
test_demo_environment.py

Unit and integration tests for the V2 Scenario Engine and demo REST routes.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from demo_scenario_engine import ScenarioEngine
from demo_routes import create_demo_router


class TestScenarioEngine:
    """Tests the enterprise scenario generator."""

    def test_startup_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("Startup")

        assert summary["profile"] == "Startup"
        assert summary["resource_count"] > 0
        assert summary["application_count"] == 3
        assert summary["monthly_cost_usd"] > 0.0

    def test_healthcare_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("Healthcare")

        assert summary["profile"] == "Healthcare"
        assert any("ehr" in r["id"] for r in engine.resources)

    def test_manufacturing_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("Manufacturing")

        assert summary["profile"] == "Manufacturing"
        assert any("dynamo" in r["id"] for r in engine.resources)

    def test_gaming_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("Gaming")

        assert summary["profile"] == "Gaming"
        assert len(engine.applications) == 2

    def test_ai_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("AI Startup")

        assert summary["profile"] == "AI Startup"
        assert len(engine.opportunities) > 0

    def test_saas_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("SaaS")

        assert summary["profile"] == "SaaS"
        assert summary["resource_count"] > 10

    def test_financial_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("Financial Services")

        assert summary["profile"] == "Financial Services"
        assert any("banking" in r["id"] for r in engine.resources)

    def test_government_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("Government")

        assert summary["profile"] == "Government"
        assert any("gov" in r["id"] for r in engine.resources)

    def test_media_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("Media")

        assert summary["profile"] == "Media"
        assert any("transcoder" in r["id"] for r in engine.resources)

    def test_retail_scenario_generation(self) -> None:
        engine = ScenarioEngine(seed=42)
        summary = engine.generate_scenario("Retail")

        assert summary["profile"] == "Retail"
        assert len(engine.applications) == 2

    def test_live_telemetry_stream(self) -> None:
        engine = ScenarioEngine()
        metrics = engine.get_live_telemetry("ec2-auth-1")

        assert metrics["target_id"] == "ec2-auth-1"
        assert 0.0 <= metrics["cpu_percent"] <= 100.0
        assert "timestamp" in metrics

    def test_copilot_responses(self) -> None:
        engine = ScenarioEngine()
        engine.generate_scenario("AI Startup")

        # GPU query on AI profile
        res_gpu = engine.get_copilot_response("show me idle GPUs")
        assert "ml-gpu-training-3" in res_gpu

        # Cost query
        res_bill = engine.get_copilot_response("why is my bill increasing?")
        assert "monthly cost of" in res_bill

        # Risk query
        res_risk = engine.get_copilot_response("find risky applications")
        assert "optimization opportunities" in res_risk or "No critical" in res_risk


class TestDemoAPIRoutes:
    """Tests demo API endpoints routes registration."""

    def test_create_router(self) -> None:
        router = create_demo_router()
        assert router is not None
        assert router.prefix == "/api/demo"

        paths = [route.path for route in router.routes]
        assert "/api/demo/health" in paths
        assert "/api/demo/scenarios" in paths
        assert "/api/demo/select" in paths
        assert "/api/demo/telemetry" in paths
        assert "/api/demo/pipeline-status" in paths
        assert "/api/demo/pipeline-start" in paths
        assert "/api/demo/copilot" in paths
