# CloudPilot SwitchOps — System Architecture

## 1. Executive Summary

**CloudPilot SwitchOps** is a Switch-native cloud engineering control room designed for the **Flip the Switch Hackathon (Track 01: Best Business Workflow)**. It allows human operators and autonomous AI agents to collaborate within a shared team-chat room to investigate infrastructure, evaluate cost/security/reliability trade-offs, approve specific modifications, execute bounded actions, and verify outcomes.

In this architecture, **Switch provides the central collaboration infrastructure**. Switch is not a cosmetic notification sink; the entire operational lifecycle originates in the Switch room and reports progress continuously back to human engineers.

---

## 2. Phase 2 Architecture Diagram

```mermaid
flowchart TD
    subgraph HumanCollaboration ["Switch Shared Collaboration Surface"]
        Human["Human Operator / Platform Engineer\n(@operator:switch)"]
        Room["Switch Room: cloudpilot-ops\n(Mattermost / Slack / Discord / Console)"]
        Human <-->|Chat / Commands: @cloudpilot-ops-agent assess ./samples/staging| Room
    end

    subgraph SwitchCore ["Switch Infrastructure"]
        Bridge["Switch Agent Bridge / Gateway\n(WebSocket + HTTP REST)"]
        Room <-->|Event Buffer & Real-time Delivery| Bridge
    end

    subgraph CloudPilotBackend ["CloudPilot SwitchOps Backend (Modular Monolith)"]
        Adapter["Switch Adapter Boundary\napp/integrations/switch\n(SwitchWireClient / EmulatedBridge)"]
        Service["Task Lifecycle & Switch Coordinator\napp/services/TaskService"]
        
        subgraph IntelligenceEngines ["Phase 2 Cloud Intelligence Engines"]
            Discovery["Infrastructure Discovery Engine\napp/services/discovery\n(TerraformParser, ComposeParser)"]
            FinOps["FinOps Intelligence Engine\napp/services/finops\n(PricingCatalog, FinOpsEngine)"]
            SecOps["SecOps & SRE Engine\napp/services/secops\n(Rules SEC-001..010, REL-001..005)"]
            
            FinOpsAgent["FinOps Specialist Agent\napp/services/specialists/FinOpsSpecialist"]
            SecOpsAgent["SecOps Specialist Agent\napp/services/specialists/SecOpsSpecialist"]
        end

        Domain["Domain Contracts & State Machine\napp/domain\n(Task, Inventory, Finding, AssessmentSummary)"]
        Persistence["Persistence Layer\napp/persistence\n(SQLiteTaskRepository)"]
        API["HTTP API Endpoints\napp/api\n(/health/*, /api/v1/tasks, /api/v1/assessments)"]

        Bridge <-->|WebSocket: Events & Pings (<=2s)\nHTTP: Outbound /message| Adapter
        Adapter <-->|Addressed Message Events| Service
        Service -->|Coordinates| Discovery
        Discovery -->|Discovered Inventory| Service
        Service -->|Dispatches| FinOpsAgent
        Service -->|Dispatches| SecOpsAgent
        FinOpsAgent --> FinOps
        SecOpsAgent --> SecOps
        Service -->|Saves State & Findings| Persistence
        Persistence --> Domain
        API --> Persistence
    end

    subgraph Storage ["CloudPilot Data Layer"]
        DB[("SQLite Database\ncloudpilot_tasks.db\n(Tasks, Events, Evidence, Inventories, Findings, Assessments)")]
        Catalog[("Pricing Catalog\ndata/pricing/catalog-v1.json\n(AWS & Docker SKUs, 730h Baseline)")]
        Persistence <--> DB
        FinOps <--> Catalog
    end
```

---

## 3. Logical Boundaries & Separation of Concerns

The backend is built as a clean, cohesive modular monolith:

1. **`app/core` (Foundation & Observability)**
   - Configuration management via `Pydantic Settings` with `.env` and environment prefixing (`CLOUDPILOT_*`).
   - Structured JSON logging with context-variable correlation IDs (`X-Correlation-ID`) and task IDs.
   - Automatic regex-based secret redaction (API keys, Bearer tokens, passwords).
   - Structured domain errors (`CloudPilotError`, `InvalidStateTransitionError`, `SwitchIntegrationError`, `ValidationError`, `NotFoundError`).

2. **`app/domain` (Domain Contracts & State Machine)**
   - Strongly typed Pydantic models for `Task`, `TaskEvent`, `Evidence`, `DiscoveredResource`, `InfrastructureInventory`, `Finding`, and `AssessmentSummary`.
   - UTC timestamp normalization on all models.
   - Enforced status lifecycle and transition validation policy.
   - Complete decoupling from transport mechanisms or external SDKs.

3. **`app/services/discovery` (Filesystem-Protected Infrastructure Discovery)**
   - Validates workspace boundaries with traversal rejection and symlink escape checks.
   - Enforces 1MB size bounds and 100-file scan limits.
   - `TerraformParser`: Safe HCL2 AST parsing, distinguishing known static literals from dynamic variable expressions (`attributes_unknown`).
   - `ComposeParser`: Safe YAML parsing with immediate regex redaction of plain secrets in environment blocks.

4. **`app/services/finops` (Deterministic Cost Intelligence)**
   - Versioned rate catalog (`data/pricing/catalog-v1.json`) with provenance tracking.
   - Decimal monetary arithmetic with `ROUND_HALF_UP` to prevent IEEE-754 precision drift.
   - Configurable monthly baseline hours (default 730 hours).
   - Rules `FIN-001` through `FIN-005` detecting instance over-sizing, unbounded limits, and idle non-production databases.

5. **`app/services/secops` (Security Posture & SRE Reliability)**
   - Deterministic rule engines evaluating rules `SEC-001` through `SEC-010` and `REL-001` through `REL-005`.
   - Attaches reproducible, defensible proof dictionaries to every finding.

6. **`app/services/specialists` (Collaborating Specialist Agents)**
   - `FinOpsSpecialist`: Evaluates cost drivers and emits intermediate Switch room breakdowns.
   - `SecOpsSpecialist`: Evaluates exposure vulnerabilities and emits intermediate Switch room posture summaries.

7. **`app/persistence` (SQLite & In-Memory Storage)**
   - Thread-safe `SQLiteTaskRepository` with foreign keys, indexing, and WAL mode.
   - Tables: `tasks`, `task_events`, `evidence`, `inventories`, `findings`, and `assessments`.
   - Read-only guarantees: the assessment lifecycle never modifies target workspace files or cloud resources.

8. **`app/integrations/switch` (Switch Wire Adapter)**
   - Decoupled `SwitchAdapterInterface`.
   - `SwitchWireClient`: Complete implementation of Switch Agent Protocol (WebSocket streaming with <=2s pings, `/message` delivery, `/agents` registration).
   - `EmulatedSwitchBridge`: Fully compliant mock for deterministic CI/CD and offline verification.
