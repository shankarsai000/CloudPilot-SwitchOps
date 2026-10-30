# CloudPilot SwitchOps — Testing Strategy & Verification Guide

## 1. Testing Philosophy

CloudPilot SwitchOps enforces rigorous automated testing. Tests must make meaningful assertions on domain invariants, protocol serialization, transactional boundaries, and state transitions. Empty or trivial tests asserting `True` are strictly prohibited.

---

## 2. Test Architecture

The test suite is structured into three logical layers:

```text
tests/
├── unit/
│   └── test_domain_and_config.py      # Domain models, state machine, config validation, logging
├── integration/
│   └── test_persistence_and_api.py   # SQLite repository, append-only history, HTTP probes & API
└── contract/
    ├── test_switch_protocol_contract.py # Switch wire protocol contracts, payloads, and workflows
    └── test_switch_websocket_wire.py    # Real in-process WebSocket server, pings (<=2s), pongs, cursor
```

---

## 3. Test Coverage Summary

### Unit Tests (`tests/unit/`)
- **Task Domain Model**: Field validation, UUID generation, UTC timestamp enforcement.
- **Task Lifecycle Transitions**:
  - `RECEIVED` -> `ACKNOWLEDGED` -> `IN_PROGRESS` -> `COMPLETED`
  - Valid failure transitions (`IN_PROGRESS` -> `FAILED`)
  - Valid cancellation paths (`RECEIVED`, `ACKNOWLEDGED`, `IN_PROGRESS` -> `CANCELLED`)
  - Rejection of invalid state jumps (e.g., `RECEIVED` -> `COMPLETED`, terminal mutations).
- **Audit Event Contract**: Append-only event model, actor categorization, schema versioning.
- **Evidence Finding Contract**: Severity classification, provenance tracking, defensible confidence validation.
- **Settings & Redaction**: Environment parsing, default validation, token and API key redaction.
- **Correlation ID Propagation**: Context variable lifecycle across calls.

### Integration Tests (`tests/integration/`)
- **SQLite Persistence**:
  - Table initialization and indexing.
  - CRUD operations with strict foreign key constraints.
  - Conflict detection for duplicate task IDs (`TaskConflictError`).
  - Missing task lookups (`TaskNotFoundError`).
- **Append-Only History**: Chronological ordering of events, immutability guarantee.
- **Evidence Persistence**: Linking findings to task IDs.
- **API Endpoints**:
  - `GET /health/live`: Process uptime and liveness.
  - `GET /health/ready`: Database and Switch connectivity probe.
  - `GET /api/v1/tasks/{task_id}`: Read-only state retrieval.
  - `GET /api/v1/tasks/{task_id}/events`: Complete audit event history.
  - `POST /api/v1/switch/simulate-message`: Diagnostic simulation of full human-agent exchange.

### Contract Tests (`tests/contract/`)
- **Switch Agent Protocol**:
  - Registration contract (`POST /agents`) and token validation.
  - Addressing rule update (`POST /agents/{agent_id}/ops/update_agent_detail`).
  - Outbound message posting (`POST /agents/{agent_id}/message`).
  - Filtering unaddressed messages (`message.addressed == False`).
  - Ignoring non-message events (presence, join).
  - Full collaborative workflow simulation.
- **Real WebSocket Wire Protocol**:
  - Starts an in-process WebSocket server simulating Switch Bridge.
  - Verifies `Authorization: Bearer` header on connection.
  - Verifies processing of `connection_state` and generation capture.
  - Verifies immediate `pong` response (`{"type": "pong", "cursor": cursor}`) within 2 seconds.
  - Verifies event delivery and clean shutdown.

---

## 4. Verification Commands & Baseline Results

### Run All Phase 1 Tests
```powershell
.venv\Scripts\pytest.exe tests -v
```
**Result**: **27 passed in 2.52s**

### Run Legacy Preserved Platform Foundation Tests
```powershell
.venv\Scripts\pytest.exe docker/tests/test_platform_foundation.py -v
```
**Result**: **29 passed in 16.59s**

### Code Formatting & Linting
```powershell
py -3.14 -m ruff check app tests
```
**Result**: **All checks passed!**
