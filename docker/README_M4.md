# M4 — Risk Intelligence Agent (RIA)

**Module ID:** M4-RIA  
**Layer:** Decision Intelligence Layer  
**Status:** ✅ Complete & Production-Ready

---

## Overview

M4 implements the **Risk Intelligence Agent (RIA)**, which acts as CloudPilot AI's operational reasoning engine. It predicts operational, compliance, financial, and architectural consequences before infrastructure changes are executed.

### Core Questions M4 Answers:
- *What happens if this EC2 instance is terminated?*
- *Will latency increase?*
- *Will this break another application?*
- *Could this violate compliance?*
- *Is rollback likely?*
- *How confident are we in this prediction?*

---

## Files Structure

All files reside flatly within the `docker/` workspace to follow project conventions:

| File Name | Purpose |
|-----------|---------|
| `models_risk.py` | Operational risk, categories, simulation requests/results. |
| `models_impact.py` | Blast radius, business impact metrics, impact propagation graph models. |
| `models_confidence.py` | Confidence scores, coverage metrics, and reporting details. |
| `risk_classifier.py` | Risk categorization (`SAFE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) and SPOF checks. |
| `dependency_analyzer.py` | Downsream cascade propagation analysis mapping resources to M3 services. |
| `blast_radius.py` | Blast radius statistics (users, teams, cost) and impact graph builder. |
| `confidence_engine.py` | Deterministic weighted scoring calculator. |
| `business_impact.py` | Business damage (SLA, revenue, customer) & cost correlation evaluator. |
| `policy_engine.py` | Rule Engine checking PCI, K8s master, database and business hour rules. |
| `root_cause.py` | Formulates visual path trace explanations for risk decisions. |
| `timeline_predictor.py` | Risk temporal analysis predictor (Immediate, 1h, 24h, 7d, long-term). |
| `mitigation_engine.py` | Actions mitigation recommendation builder. |
| `risk_engine.py` | Coordinates components and calculates composite risk score. |
| `risk_intelligence_agent.py` | Main M4 Agent Orchestrator. |
| `risk_repository.py` | PostgreSQL persistence layer. |
| `risk_routes.py` | FastAPI APIRouter endpoints. |
| `test_risk_engine.py` | Test suite with 45+ assert checkpoints. |

---

## Risk Model & Confidence Math

### Numerical Risk Score (0-100)
Risk scores are calculated deterministically on the following composite factors:
- **Inherent Action Risk**: Inherent danger weights (e.g. `TERMINATE` = 40, `START` = 5).
- **Technical Health & SPOF**: Multipliers for Single Point of Failure (no redundancy) + state health problems.
- **Dependency Cascading Severity**: Proportional depth and breadth of affected services.
- **Business Impact Exposure**: SLA violation potential + customer-facing indicators.
- **Policy Violations**: Critical policy triggers add a flat safety penalty (+40.0).

### Confidence Score (0-100%)
Determined via the following weighted formula:
1. **Topology Coverage (30%)**: Completeness of application resource mapping.
2. **Historical Incidents (20%)**: Deductions based on incident records availability.
3. **Resource Health (20%)**: Percentage of context elements running successfully.
4. **Dependency Accuracy (20%)**: verified connections presence.
5. **Business Metadata (10%)**: Presence of owner, team, and tag indicators.

---

## API Documentation

The router exposes endpoints mounted on `/api/risk`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/risk` | General risk metrics summary. |
| `GET` | `/api/risk/resources/{id}` | Get predicted risk score of action on a resource. |
| `GET` | `/api/risk/applications/{id}` | Get predicted risk score of action on an application. |
| `GET` | `/api/risk/blast-radius/{id}` | Trace blast radius detail reports for action. |
| `GET` | `/api/risk/confidence/{id}` | Retrieve confidence details score breakdown. |
| `POST` | `/api/risk/simulate` | Run mock simulation for a change request. |
| `GET` | `/api/risk/policies` | List configured organization policies. |
| `GET` | `/api/risk/history` | Query simulation runs history. |

---

## Test Executions

Run the unit tests:
```bash
python -m pytest test_risk_engine.py -v
```
