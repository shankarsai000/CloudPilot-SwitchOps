# M3 — Application Intelligence Agent (AIA)

**Module ID:** M3-AIA  
**Layer:** Business Intelligence Layer  
**Status:** ✅ Complete & Production-Ready

---

## Overview

M3 transforms raw cloud infrastructure (from M1) into **business-aware applications**.

| Module | Question |
|--------|----------|
| M1 — Infrastructure Discovery | What infrastructure exists? |
| M2 — Cost Intelligence | How much does it cost? |
| **M3 — Application Intelligence** | **Why does this infrastructure exist?** |

### Before M3
```
EC2-001, RDS-023, ALB-12, Lambda-45
```

### After M3
```
Payment Service
├── EC2-001  (backend)
├── RDS-023  (database)
├── ALB-12   (load balancer)
└── Lambda-45 (backend)

Owner: jane.doe @ Payments Team
Criticality: 92.5/100 (CRITICAL)
Cost: $1,250/month
```

---

## Architecture

```
M1 ResourceGraph ──► ApplicationDiscoveryEngine
                          │
                          ▼
                     DependencyMapper ──► ServiceGraph (networkx)
                          │
                          ▼
                    TopologyBuilder ──► ApplicationTopology
                          │
                          ▼
                    OwnershipMapper ──► OwnershipInfo
                          │
                          ▼
                   DeploymentAnalyzer ──► DeploymentRecords + DORA
                          │
                          ▼
                    TrafficMapper ──► TrafficFlows
                          │
                          ▼
                  BusinessContextEngine ──► BusinessCriticality
                          │
                          ▼
                   ApplicationGraph ──► REST API
```

---

## Files

| File | Purpose | Lines |
|------|---------|-------|
| `models_application.py` | Core models: Application, ServiceNode, etc. | ~420 |
| `models_topology.py` | TopologyNode, TopologyEdge, layers | ~200 |
| `models_dependency.py` | DependencyGraphNode, edges, cycles | ~180 |
| `models_ownership.py` | TeamInfo, OwnershipMapping, reports | ~180 |
| `application_discovery.py` | Strategy-based resource grouping | ~350 |
| `service_graph.py` | networkx-backed graph with traversal | ~300 |
| `dependency_mapper.py` | Infers service dependencies from M1 | ~300 |
| `topology_builder.py` | Layer classification, topology building | ~220 |
| `ownership_mapper.py` | Tag/annotation/registry ownership resolution | ~280 |
| `deployment_analyzer.py` | Deployment tracking, DORA metrics | ~300 |
| `observability_connector.py` | Prometheus/Datadog/OTel adapters | ~320 |
| `traffic_mapper.py` | Ingress/egress/internal traffic flows | ~200 |
| `business_context.py` | Weighted criticality scoring engine | ~310 |
| `graph_exporter.py` | Dict/adjacency/Mermaid export | ~250 |
| `application_intelligence_agent.py` | Main orchestrator (8-stage pipeline) | ~280 |
| `application_repository.py` | PostgreSQL persistence (Repository pattern) | ~350 |
| `application_routes.py` | FastAPI REST endpoints (10 endpoints) | ~450 |
| `test_application_agent.py` | Comprehensive test suite (49+ tests) | ~650 |

**Total: 18 files | ~5,500 lines | 49+ unit tests**

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/applications` | GET | List all applications (filtering by type, env, tier) |
| `/api/applications/{id}` | GET | Get application details |
| `/api/applications/{id}/topology` | GET | Get application topology (nodes, edges, layers) |
| `/api/applications/{id}/dependencies` | GET | Get dependency graph (cycles, critical path) |
| `/api/applications/{id}/services` | GET | List services within application |
| `/api/applications/{id}/owners` | GET | Get ownership information |
| `/api/applications/{id}/criticality` | GET | Get business criticality scores |
| `/api/applications/discover` | POST | Trigger manual discovery |
| `/api/applications/health` | GET | Health check |
| `/api/applications/stats` | GET | Statistics summary |

---

## Core Capabilities

### 1. Application Discovery
Four pluggable strategies (Strategy pattern):
- **Tag-based** — Groups by `app`, `application`, `service` tags
- **Namespace** — Groups K8s resources by namespace
- **Naming convention** — Groups by naming prefix patterns
- **Label** — Groups by `app.kubernetes.io/name` labels

### 2. Service Dependency Graph
networkx-backed directed graph with:
- Topological ordering
- Cycle detection
- Blast radius analysis
- Critical path identification
- Subgraph extraction

### 3. Ownership Resolution
Multi-source resolution with confidence scoring:
- Resource tags (90% confidence)
- K8s annotations (80% confidence)
- Team registry (50% confidence)
- Coverage reports

### 4. Business Criticality
Weighted scoring model (0-100):
- Revenue impact (25%)
- Compliance impact (20%)
- Availability target (20%)
- Recovery priority (15%)
- Risk level (20%)

### 5. Deployment Intelligence
- Deployment frequency, history, failure rate
- Strategy detection (canary, blue/green, rolling)
- DORA metrics (frequency, lead time, failure rate, MTTR)
- Performance classification (elite, high, medium, low)

### 6. Traffic Flow Intelligence
- Ingress flows (external → app)
- Egress flows (app → external)
- Internal flows (service → service)
- RPS, latency, error rate metrics

### 7. Observability Integration
Adapter pattern for monitoring platforms:
- Prometheus
- Datadog
- OpenTelemetry (Jaeger, Elastic, New Relic)

---

## Integration Guide

### M1 → M3
```python
from infrastructure_discovery_agent import DiscoveryAgent
from application_intelligence_agent import ApplicationIntelligenceAgent

# Discover infrastructure
m1 = DiscoveryAgent()
resource_graph = m1.discover()

# Discover applications
m3 = ApplicationIntelligenceAgent()
app_graph = m3.discover_applications(resource_graph)
```

### M2 → M3 (Optional Enrichment)
```python
# Enrich with cost data (loosely coupled)
cost_data = {"res-id-1": 150.0, "res-id-2": 85.0}
m3.enrich_from_cost_data(cost_data)
```

### M3 → M4 (Future)
```python
# M4 consumes M3's API directly
app = m3.get_application("app-payment-service")
topology = m3.get_application_topology("app-payment-service")
dependencies = m3.get_application_dependencies("app-payment-service")
```

---

## Design Patterns

| Pattern | Usage |
|---------|-------|
| **Strategy** | Pluggable discovery strategies |
| **Adapter** | Observability platform connectors |
| **Repository** | PostgreSQL persistence layer |
| **Factory** | Cloud adapter creation (from M1) |
| **Dependency Injection** | All agent sub-components injected |
| **Graph** | networkx-based service dependency graph |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `networkx` | Service dependency graph algorithms |
| `pydantic` | Model validation (already in M1/M2) |
| `fastapi` | REST API (already in M1/M2) |
| `pytest` | Testing (already in M1/M2) |

---

## Running Tests

```bash
cd docker
python -m pytest test_application_agent.py -v
```

---

## Configuration

M3 requires no additional configuration files. It consumes:
- M1 `ResourceGraph` via Python API
- M2 cost data via optional `enrich_from_cost_data()` call
- External data sources via Observability adapters (mocked in dev)

Environment variables for production:
```bash
# PostgreSQL (for ApplicationRepository)
DATABASE_URL=postgresql://user:pass@host:5432/cloudpilot

# Observability (optional)
PROMETHEUS_URL=http://prometheus:9090
DATADOG_API_KEY=your-key
DATADOG_APP_KEY=your-key
```
