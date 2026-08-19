# M5 — Strategic Decision Agent (SDA)

**Module ID:** M5-SA  
**Layer:** Strategic Decision Intelligence Layer  
**Status:** ✅ Complete & Production-Ready

---

## Overview

M5 implements the **Strategy Agent (SA)**, which acts as CloudPilot AI's Principal Cloud Architect. It aggregates cost, infrastructure, application topologies, and operational risk metrics to synthesize holistic optimization proposals.

Instead of generating simple recommendations, M5 designs **comprehensive Optimization Plans** detailing candidates, payback periods, cascading dependencies, and automated blueprints.

---

## Files Structure

All M5 components are located flat in the `docker/` workspace:

| File Name | Purpose |
|-----------|---------|
| `models_strategy.py` | Pydantic structures for candidate strategies, roadmaps, portfolios, scenarios, and plans. |
| `opportunity_detector.py` | Scans systems for underutilization, zombies, static replicas, and low operations. |
| `roi_calculator.py` | Computes financial payback days, engineering hours, and ROI indices. |
| `priority_engine.py` | Configurable weighted scoring matrix generator. |
| `recommendation_generator.py` | Compiles comparative alternatives and trade-off details. |
| `roadmap_builder.py` | Organizes actions into weekly timelines (Compute -> Storage -> Networking). |
| `dependency_planner.py` | Chains pre/post instructions (Snapshots, metrics validation). |
| `approval_engine.py` | Specifications sorting workflows (`AUTO_EXECUTE`, `APPROVAL_REQUIRED`, `BLOCKED`). |
| `whatif_engine.py` | Parameterized scenario simulations (Traffic drops, regional expansions). |
| `portfolio_builder.py` | Categorizes plans into tactical portfolio columns. |
| `strategy_engine.py` | Coordinates components to build unified plans. |
| `strategy_agent.py` | Main M5 Agent Orchestrator. |
| `strategy_repository.py` | PostgreSQL persistence. |
| `strategy_routes.py` | FastAPI APIRouter endpoints. |
| `test_strategy_agent.py` | Unit tests with 45+ assert checkpoints. |

---

## Strategy Scoring Formula

 prioritizing scores (0-100) are generated using the following default weights:
- **ROI Score (30%)**: Savings relative to implementation engineering costs.
- **Risk Level (25%)**: Qualitatively mapped from M4 scores (SAFE = 100, CRITICAL = 0).
- **Business Value (20%)**: Directly correlates with application tier and criticality.
- **Confidence Rating (15%)**: From M4 calculations.
- **Complexity (10%)**: Implementation effort mapping (LOW = 100, HIGH = 20).

These weights can be customized during `PriorityEngine` instantiation.

---

## API Documentation

M5 endpoints are registered on `/api/strategies`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/strategies` | Retrieve all current optimization strategies. |
| `GET` | `/api/strategies/{id}` | Retrieve details of a specific plan. |
| `POST` | `/api/strategies/generate` | Trigger the generation of new plans. |
| `POST` | `/api/strategies/whatif` | Simulates what-if scenarios (e.g. traffic drop). |
| `GET` | `/api/strategies/portfolio` | Retrieve plans organized into portfolio columns. |
| `GET` | `/api/strategies/roadmap` | Get phased optimization roadmaps. |
| `GET` | `/api/strategies/priorities` | Get ranked priority items. |
| `GET` | `/api/strategies/roi` | Retrieve ROI metrics reports. |

---

## Running Tests

Run the test suite:
```bash
python -m pytest test_strategy_agent.py -v
```
