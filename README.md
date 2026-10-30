# CloudPilot SwitchOps
### Switch-Native Autonomous Cloud Engineering Control Room

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Switch AI Native](https://img.shields.io/badge/Switch-Native%20Integration-6366f1.svg)](https://switchagents.ai/)
[![Tests Passing](https://img.shields.io/badge/Phase%201%20Tests-27%20Passed-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey.svg)](LICENSE)

> Built for the **Flip the Switch Hackathon — Track 01: Best Business Workflow**  
> Hackathon details: [wemakedevs.org/hackathons/switch](https://www.wemakedevs.org/hackathons/switch)  
> Switch Documentation: [docs.switchagents.ai](https://docs.switchagents.ai/)

---

## 1. What CloudPilot SwitchOps Does

**CloudPilot SwitchOps** transforms disjointed cloud operations into a shared, collaborative control room inside **Switch AI**. 

Instead of isolating human operators inside complex dashboards and autonomous agents inside CLI silos, CloudPilot SwitchOps unites human engineers and specialized AI agents in a shared Switch team-chat room (`cloudpilot-ops`). Together, they:
1. **Investigate cloud infrastructure** across cost, security, and reliability dimensions.
2. **Evaluate trade-offs** using verifiable evidence findings and counterfactual simulations.
3. **Govern modifications** through explicit human-in-the-loop approvals.
4. **Execute bounded actions** through sandboxed GitOps and cloud adapters.
5. **Verify outcomes** with continuous post-execution monitoring and deterministic rollback.

---

## 2. Business Problem Addressed

Modern enterprise cloud management suffers from **The Operational Hand-off Gap**:
- **Siloed Tooling**: FinOps, SecOps, and Platform Engineering tools produce disjointed alerts and spreadsheets that lack business context.
- **Runaway Cloud Costs**: Infrastructure drifts silently with idle instances, unattached volumes, and over-provisioned clusters without unified review.
- **Fear of Autonomous Changes**: Operators distrust black-box AI tools that attempt to modify production infrastructure without auditable consensus or human gating.
- **Context Loss**: Change decisions made in ticket queues or private chats lack cryptographic audit trails linking the initial problem to the final verified outcome.

**CloudPilot SwitchOps solves this by anchoring all operational collaboration in Switch**. Every request, acknowledgment, evidence finding, risk assessment, human approval, and execution summary lives in the shared Switch room history and an append-only database audit log.

---

## 3. Why Switch is Essential (Switch Centrality)

Switch is the foundational collaboration infrastructure for CloudPilot SwitchOps. **It is not a decorative chat plugin.**

### The Switch Centrality Test
> *"If Switch is unavailable, can a human still complete the same collaborative workflow through a separate application interface?"*  
> **The answer is NO.**

- **Shared Collaboration Surface**: The human-agent conversational handoff, intent capture, room instructions, and progress notifications strictly require Switch.
- **Identity & Addressing**: Switch handles participant identity (`@operator:switch`), permissions, and addressed message routing (`message.addressed`).
- **Unified Wire Protocol**: CloudPilot communicates with Switch using the official bidirectional wire protocol (WebSocket streaming for incoming events and HTTP for outbound messaging).
- CloudPilot exposes health diagnostics and read-only state endpoints for operators, but does not provide a rogue chat interface bypassing Switch.

---

## 4. System Architecture

```mermaid
flowchart TD
    subgraph HumanCollaboration ["Switch Shared Collaboration Surface"]
        Human["Human Operator / Platform Engineer\n(@operator:switch)"]
        Room["Switch Room: cloudpilot-ops\n(Mattermost / Slack / Discord / Console)"]
        Human <-->|Chat & Commands| Room
    end

    subgraph SwitchCore ["Switch Infrastructure"]
        Bridge["Switch Agent Bridge / Gateway\n(WebSocket + HTTP REST)"]
        Room <-->|Event Buffer & Delivery| Bridge
    end

    subgraph CloudPilotBackend ["CloudPilot SwitchOps Backend (Modular Monolith)"]
        Adapter["Switch Wire Adapter\napp/integrations/switch\n(SwitchWireClient / EmulatedBridge)"]
        Service["Task Lifecycle & Orchestration\napp/services/TaskService"]
        Domain["Domain Contracts & Transition Policy\napp/domain\n(Task, TaskEvent, Evidence)"]
        Persistence["Persistence Layer\napp/persistence\n(SQLiteTaskRepository)"]
        API["HTTP API & Health Probes\napp/api\n(/health/live, /health/ready, /api/v1/tasks)"]

        Bridge <-->|WebSocket: Events & Pings (<=2s)\nHTTP: Outbound /message| Adapter
        Adapter <-->|Addressed Message Events| Service
        Service -->|Enforces State Machine| Domain
        Service -->|Append-Only Events & Metadata| Persistence
        API -->|Read Probes & State| Persistence
        API -->|Readiness Probe| Adapter
    end

    subgraph Storage ["CloudPilot Data Layer"]
        DB[("SQLite Database\ncloudpilot_tasks.db\n(Tasks, Events, Evidence)")]
        Persistence <--> DB
    end
```

### Architectural Principles Enforced:
1. **Decoupled Domain**: Domain logic never imports or depends directly on Switch wire transport or third-party SDKs.
2. **Explicit State Machine**: Task lifecycles follow a strict transition policy (`RECEIVED` → `ACKNOWLEDGED` → `IN_PROGRESS` → `COMPLETED`).
3. **Append-Only Auditing**: Every milestone emits an immutable `TaskEvent` stored with UTC timestamps and correlation IDs.
4. **Secret Protection**: Bearer tokens, API keys, and sensitive configuration are masked in logs and excluded from serialization.

---

## 5. Switch Installation & Setup

1. **Install Switch Console**:
   Download and install the desktop application for Windows, macOS, or Linux from [switchagents.ai](https://switchagents.ai/).
2. **Configure Provider & Workspace**:
   Open Switch Console and let the setup checklist guide you through your agent provider connection.
3. **Start the Agent Bridge**:
   Switch Console runs the Agent Bridge locally (default: `http://localhost:8080`).

---

## 6. How to Connect the CloudPilot Agent

### Option A: Automatic Registration
Configure your `.env` with your Switch deployment registration key:
```env
CLOUDPILOT_SWITCH_BRIDGE_URL="http://localhost:8080"
CLOUDPILOT_SWITCH_REGISTRATION_KEY="<your-registration-token>"
CLOUDPILOT_SWITCH_AGENT_NAME="cloudpilot-ops-agent"
```
On boot, CloudPilot registers via `POST /agents` and stores its permanent `api_key`.

### Option B: Pre-Registered Credentials
If the agent was already registered in Switch Console:
```env
CLOUDPILOT_SWITCH_BRIDGE_URL="http://localhost:8080"
CLOUDPILOT_SWITCH_AGENT_ID="<agent-id>"
CLOUDPILOT_SWITCH_AGENT_API_KEY="<agent-api-key>"
```

### Option C: Offline / Standalone Emulation
If running in an isolated environment without Switch Console running, CloudPilot automatically boots the internal **EmulatedSwitchBridge**, enabling full local testing with 100% deterministic fidelity.

---

## 7. The Operations Room (`cloudpilot-ops`)

1. In Switch Console or Gateway, create a new room:
   - **Name**: `cloudpilot-ops`
   - **Topic**: `CloudPilot Autonomous Cloud Operations Control Room`
   - **Instructions**:
     ```text
     You are collaborating with CloudPilot SwitchOps to review cloud infrastructure,
     evaluate cost and security trade-offs, and manage change approvals.
     Always enforce least-privilege read-only defaults.
     ```
2. Add `@cloudpilot-ops-agent` to the room.

---

## 8. First End-to-End Workflow

In the `cloudpilot-ops` room, a human operator posts:
```text
@CloudPilot review the staging infrastructure for a cost and security assessment. Do not modify any files or infrastructure.
```

### Execution Flow:
1. **Receive**: Switch pushes the addressed message frame over WebSocket (`GET /agents/{id}/connection/ws`).
2. **Identify**: CloudPilot validates the prompt and extracts the request into a new `Task` in `RECEIVED` status.
3. **Acknowledge**: CloudPilot transitions to `ACKNOWLEDGED` and immediately posts to the room:
   ```text
   [CloudPilot SwitchOps] Acknowledged request: Review staging infrastructure...
   - Task ID: task-4953af7e3e0a
   - Status: ACKNOWLEDGED
   - Correlation ID: corr-ba31fbf2d85a
   ```
4. **Execute**: CloudPilot transitions to `IN_PROGRESS`, records a `TASK_STARTED` event, and executes the Phase 1 read-only review baseline.
5. **Report**: CloudPilot transitions to `COMPLETED`, records `TASK_COMPLETED`, and posts the final truthful outcome in the room:
   ```markdown
   ### [CloudPilot SwitchOps] Task Execution Report
   - **Task ID**: `task-4953af7e3e0a`
   - **Status**: `COMPLETED`
   - **Requested by**: @operator:switch
   - **Room**: `cloudpilot-ops`
   - **Correlation ID**: `corr-ba31fbf2d85a`

   **Assessment Outcome:**
   CloudPilot SwitchOps Phase 1 Foundation Verified.
   - Read-only policy enforced: zero modifications made to files or infrastructure.
   - Live multi-cloud discovery & FinOps/SecOps intelligence engines will activate in Phase 2.
   - Switch collaboration bridge and task audit trail are verified active.
   ```

---

## 9. Running the Application

### Setup Environment
```powershell
# Create & activate venv
uv venv --python 3.11 .venv
.venv\Scripts\activate

# Install dependencies
uv pip install fastapi uvicorn pydantic pydantic-settings pytest pytest-asyncio httpx websockets sqlalchemy boto3 networkx

# Copy configuration template
Copy-Item .env.example .env
```

### Start Server
```powershell
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Diagnostic Endpoints
- **Liveness Probe**: `GET http://localhost:8000/health/live`
- **Readiness Probe**: `GET http://localhost:8000/health/ready`
- **Task Lookup**: `GET http://localhost:8000/api/v1/tasks/{task_id}`
- **Audit Events**: `GET http://localhost:8000/api/v1/tasks/{task_id}/events`
- **Diagnostic Simulation**: `POST http://localhost:8000/api/v1/switch/simulate-message`
- **Swagger Documentation**: `http://localhost:8000/docs`

---

## 10. Running Tests

Run all Phase 1 tests (Unit, Integration, Contract):
```powershell
.venv\Scripts\pytest.exe tests -v
```
**Test Results**: **27 passed in 2.52s**

Run preserved CloudPilot foundation tests:
```powershell
.venv\Scripts\pytest.exe docker/tests/test_platform_foundation.py -v
```
**Test Results**: **29 passed in 16.59s**

Run code quality & linting:
```powershell
ruff check app tests
```
**Result**: **All checks passed!**

---

## 11. Phase 1 Implementation Scope & Status

### Implemented & Verified in Phase 1:
- [x] Complete repository audit and baseline test verification.
- [x] Modular monolith architecture (`app/core`, `app/domain`, `app/persistence`, `app/integrations`, `app/services`, `app/api`).
- [x] Strongly typed settings with Pydantic Settings, environment validation, and secret redaction.
- [x] Structured JSON logging with correlation ID and task ID context tracking.
- [x] Standard operational liveness and readiness probes (`/health/live`, `/health/ready`).
- [x] Typed domain contracts (`Task`, `TaskEvent`, `Evidence`).
- [x] Strict state machine enforcing allowed lifecycle transitions.
- [x] Thread-safe SQLite persistence with foreign keys and append-only event logging.
- [x] Documented Switch Agent Protocol wire client (`SwitchWireClient`) with WebSocket streaming and mandatory 2-second heartbeat responses.
- [x] Fully compliant emulated bridge (`EmulatedSwitchBridge`) for deterministic local testing.
- [x] Real Switch room collaborative workflow (`cloudpilot-ops`).
- [x] Comprehensive test suites (27 unit, integration, and contract tests).
- [x] Preserved legacy multi-cloud code without destructive rewrites.

### Deliberately Deferred to Later Phases (Out of Scope for Phase 1):
- **Phase 2**: Live AWS/Azure/GCP account discovery & billing API integrations.
- **Phase 3**: Unified FinOps/SecOps intelligence pipeline & counterfactual simulation.
- **Phase 4**: Human-in-the-loop approval routing & sandboxed GitOps execution.
- **Phase 5**: Post-execution outcome verification & deterministic rollback.

---

## 12. Documentation Index

- [Architecture Guide](docs/architecture.md): Deep-dive into modular boundaries, state machines, and Switch centrality.
- [Switch Integration Guide](docs/switch-integration.md): Wire protocol specification, frame catalog, heartbeat mechanics, and room setup.
- [Development Setup](docs/development-setup.md): Local environment setup, commands, and troubleshooting.
- [Configuration Reference](docs/configuration.md): Complete reference for environment variables and secrets.
- [Testing Guide](docs/testing.md): Automated testing strategy, test layers, and verification commands.
