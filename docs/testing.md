# CloudPilot SwitchOps — Testing Strategy & Verification Guide

## 1. Testing Philosophy

CloudPilot SwitchOps enforces rigorous automated testing. Tests make meaningful assertions on domain invariants, protocol serialization, transactional boundaries, state transitions, filesystem security bounds, Decimal monetary math, and deterministic rule triggers.

---

## 2. Test Architecture

The test suite is structured across logical layers:

```text
tests/
├── unit/
│   ├── test_domain_and_config.py      # Domain models, state machine, config validation, logging
│   ├── test_discovery_parsers.py      # Terraform HCL & Compose parsers, filesystem bounds, traversal checks
│   ├── test_finops_engine.py          # Pricing catalog, Decimal arithmetic, monthly hours, rules FIN-001..FIN-005
│   └── test_secops_engine.py          # Rules SEC-001..SEC-010, REL-001..REL-005, staging and safe verification
├── integration/
│   ├── test_persistence_and_api.py   # SQLite repository, append-only history, HTTP probes & API
│   ├── test_assessment_workflow.py   # Full Switch-addressed assessment workflow, room updates, read-only proof
│   └── test_assessment_api.py        # REST endpoints: run assessment, inventory, findings, cost breakdown
└── contract/
    ├── test_switch_protocol_contract.py # Switch wire protocol contracts, payloads, and workflows
    └── test_switch_websocket_wire.py    # Real in-process WebSocket server, pings (<=2s), pongs, cursor fencing
```

---

## 3. Test Coverage Summary (71 Passing Automated Tests)

### Unit Tests (`tests/unit/`) — 25 Tests
- **Domain & Lifecycle**: Status state machine (`RECEIVED` -> `ACKNOWLEDGED` -> `IN_PROGRESS` -> `COMPLETED`), rejection of illegal transitions, UTC timestamp normalization.
- **Audit & Evidence Contracts**: Task events, evidence structures, defensible confidence scoring (0.0 to 1.0).
- **Settings & Security**: Config hierarchy, correlation ID context propagation, secret redaction (`[REDACTED]`).
- **Discovery Parsers**:
  - HCL2 parsing of EC2, EBS, RDS, S3, Security Groups.
  - Distinguishing known static literals from dynamic variable expressions (`attributes_unknown`).
  - Docker Compose safe YAML parsing, port bindings, volumes, capabilities, and secret redaction.
  - Filesystem traversal rejection (`../`), symlink bounds, non-existent workspace detection.
- **FinOps Intelligence**:
  - Catalog indexing from `data/pricing/catalog-v1.json`.
  - Rate lookups by exact SKU and resource type fallback.
  - Exact Decimal monetary calculation (730 baseline hours) eliminating floating point drift.
  - Triggers for `FIN-001`, `FIN-002`, `FIN-003`, `FIN-004`, `FIN-005`.
  - Sizing rightsizing verification on `samples/safe` (zero over-sizing findings).
- **SecOps & SRE Rules**:
  - Verification of `SEC-001` through `SEC-010` on `samples/staging`.
  - Verification of `REL-001` through `REL-005` on `samples/staging`.
  - Zero critical/high vulnerabilities verified on `samples/safe`.

### Integration Tests (`tests/integration/`) — 10 Tests
- **SQLite Persistence**: Thread-safe task creation, conflict handling, updates, append-only event logs.
- **End-to-End Switch Assessment Workflow**:
  - Operator prompt `@cloudpilot-ops-agent assess ./samples/staging for cost, security and reliability risks. Read-only.`
  - Emitted message stream: Acknowledgment -> Discovery Start -> Discovery Completed -> FinOps Report -> SecOps Report -> Consolidated Assessment.
  - Verification of persisted inventory, findings, and assessment summary in SQLite.
  - Strict read-only verification: asserts zero modification of file stat mtimes on target workspace files.
- **Assessment REST API**:
  - `POST /api/v1/assessments/run`: Triggering autonomous assessment.
  - `GET /api/v1/assessments/{task_id}`: Consolidated assessment summary retrieval.
  - `GET /api/v1/assessments/{task_id}/inventory`: Discovered resources inspection.
  - `GET /api/v1/assessments/{task_id}/findings`: Category and severity filtering.
  - `GET /api/v1/assessments/{task_id}/findings/{finding_id}`: Single finding detail.
  - `GET /api/v1/assessments/{task_id}/cost-breakdown`: Itemized monthly costs.

### Contract Tests (`tests/contract/`) — 7 Tests
- **Switch Protocol Contracts**:
  - Registration contract (`POST /agents`), addressing permissions (`POST /agents/{agent_id}/ops/update_agent_detail`).
  - Outbound message posting (`POST /agents/{agent_id}/message`).
  - Inbound addressed message filtering (`payload.addressed == True`).
  - Complete human-agent collaborative exchange in room `cloudpilot-ops`.
- **WebSocket Wire Protocol**:
  - Real asyncio WebSocket server and client exchange.
  - Connection handshake with `expected_generation` fencing.
  - Server ping frame handling with immediate pong response carrying highest cursor sequence (`<= 2s`).

### Preserved Foundation Tests (`docker/tests/test_platform_foundation.py`) — 29 Tests
- Configuration management, JSON/console log formatters, error handling with test app, database session lifecycle, in-memory Redis, JWT authentication, RBAC permission evaluation, health probes, metrics, and event bus.

---

## 4. Running the Tests

Execute the complete 71-test regression suite:

```powershell
# Run all Phase 1 and Phase 2 tests
.venv\Scripts\pytest.exe tests -v

# Run the complete test suite including preserved foundation tests
.venv\Scripts\pytest.exe tests docker/tests/test_platform_foundation.py -v
```
