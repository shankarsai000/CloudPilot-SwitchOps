# CloudPilot SwitchOps
### Switch-Native Autonomous Cloud Engineering Control Room

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Switch AI Native](https://img.shields.io/badge/Switch-Native%20Integration-6366f1.svg)](https://switchagents.ai/)
[![Tests Passing](https://img.shields.io/badge/Phase%202%20Tests-71%20Passed-brightgreen.svg)](tests/)
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
- **Specialist Multi-Agent Team**: Specialist agents (`finops-specialist`, `secops-specialist`) post intermediate audit findings and breakdowns directly into the Switch room thread.
- **Identity & Addressing**: Switch handles participant identity (`@operator:switch`), permissions, and addressed message routing (`message.addressed`).
- **Unified Wire Protocol**: CloudPilot communicates with Switch using the official bidirectional wire protocol (WebSocket streaming for incoming events and HTTP for outbound messaging).
- CloudPilot exposes health diagnostics and read-only state endpoints for operators, but does not provide a rogue chat interface bypassing Switch.

---

## 4. Phase 2 System Architecture

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
        
        subgraph IntelligenceEngines ["Cloud Intelligence Engines"]
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

## 5. Phase 2 Cloud Intelligence Capabilities

### A. Infrastructure Discovery Engine (`app.services.discovery`)
- **Filesystem Security**: Rejects directory traversal (`../`), symlink escapes, bounds files to 1MB, and caps workspace scans at 100 files.
- **Terraform HCL Parser**: Parses EC2, EBS, RDS, S3, Security Groups, ALBs. Distinguishes known static literals from dynamic variable expressions (`attributes_unknown`).
- **Docker Compose Parser**: Parses services, images, port publishing, volumes, resource limits, capabilities, with automated regex secret redaction (`[REDACTED]`).
- **Read-Only Invariant**: Never executes code, mutations, or cloud write APIs.

### B. FinOps Intelligence Engine (`app.services.finops`)
- **Decimal Monetary Arithmetic**: Uses Python's `Decimal` with `ROUND_HALF_UP` quantization to eliminate IEEE-754 precision drift.
- **Versioned Pricing Catalog**: Rate cards from `data/pricing/catalog-v1.json` modeling 730 standard monthly operating hours.
- **Rules Evaluated**:
  - `FIN-001`: Oversized compute instance (`m5.large`, `c5.xlarge`) in non-production.
  - `FIN-002`: Missing CPU/memory resource limits on container services.
  - `FIN-003`: Always-on staging database without off-hours auto-pause.
  - `FIN-004`: Dynamic or unresolved pricing expressions requiring baseline fallback.
  - `FIN-005`: Provisioned IOPS (`io2`) storage where general purpose (`gp3`) suffices.

### C. SecOps & SRE Reliability Engine (`app.services.secops`)
- **Security Rules**:
  - `SEC-001`: Redis bound to public interface `0.0.0.0:6379`.
  - `SEC-002`: Database listener port (5432, 3306) publicly published.
  - `SEC-003`: Security group with unrestricted `0.0.0.0/0` ingress on sensitive ports.
  - `SEC-004`: Privileged container mode enabled (`privileged: true`).
  - `SEC-005`: Docker socket mount (`/var/run/docker.sock`).
  - `SEC-006`: Host network mode enabled (`network_mode: host`).
  - `SEC-007`: S3 bucket with public ACL or missing public access block.
  - `SEC-008`: Unencrypted EBS volume.
  - `SEC-009`: Unencrypted RDS instance.
  - `SEC-010`: Plain-text sensitive credential committed in configuration.
- **SRE & Reliability Rules**:
  - `REL-001`: Missing container healthcheck.
  - `REL-002`: Suboptimal or absent restart policy.
  - `REL-003`: Single Point of Failure (single-AZ RDS database).
  - `REL-004`: Missing container resource limits (noisy neighbor risk).
  - `REL-005`: Stateful database service missing persistent volume storage.

---

## 6. Demonstration Scenarios

The repository includes realistic infrastructure scenarios in `samples/`:

1. **`samples/staging` (Deliberate Architectural Trade-Offs)**:
   - Terraform configuration declaring an oversized `m5.large` instance, `io2` provisioned IOPS storage, unencrypted `aws_db_instance`, public S3 bucket, and unrestricted security group ingress (`0.0.0.0/0`).
   - Docker Compose file declaring unauthenticated Redis on `0.0.0.0:6379`, Postgres with hardcoded password and no persistent volume, and a privileged daemon mounting `/var/run/docker.sock`.
   - **Assessment Outcome**: Flags 10 security issues, 5 reliability deficits, 4 FinOps flags, and \$212.83/mo baseline.

2. **`samples/safe` (Hardened, Rightsized Baseline)**:
   - Rightsized `t3.micro` instance, `gp3` encrypted storage, multi-AZ encrypted RDS, private S3 bucket with `aws_s3_bucket_public_access_block`, restricted ingress CIDR (`10.0.1.0/24`), healthchecked container services with persistent volumes.
   - **Assessment Outcome**: Zero critical or high security findings, \$38.25/mo baseline.

---

## 7. Switch Team Room Workflow

1. In the `cloudpilot-ops` Switch room, an operator submits:
   ```text
   @cloudpilot-ops-agent assess ./samples/staging for cost, security and reliability risks. Read-only assessment. Do not modify anything.
   ```
2. The agent executes through a transparent multi-message stream:
   - **Acknowledgment**: Immediately confirms request and task ID.
   - **Discovery Progress**: Reports discovered configuration files, resource count, and scan duration.
   - **FinOps Report**: `finops-specialist` posts itemized monthly spend and sizing optimization flags.
   - **SecOps Report**: `secops-specialist` posts vulnerability severity breakdown and critical findings.
   - **Consolidated Assessment**: Final executive summary with prioritized recommendations for Phase 3 optimization.

---

## 8. Running the Application & APIs

### Start Server
```powershell
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Assessment API Endpoints
- **Run Assessment**: `POST http://localhost:8000/api/v1/assessments/run`
- **Get Assessment**: `GET http://localhost:8000/api/v1/assessments/{task_id}`
- **Get Discovered Inventory**: `GET http://localhost:8000/api/v1/assessments/{task_id}/inventory`
- **Filter Findings**: `GET http://localhost:8000/api/v1/assessments/{task_id}/findings?category=FINOPS&severity=CRITICAL`
- **Cost Breakdown**: `GET http://localhost:8000/api/v1/assessments/{task_id}/cost-breakdown`
- **Swagger Documentation**: `http://localhost:8000/docs`

---

## 9. Running Tests

Run all Phase 1 and Phase 2 tests (Unit, Integration, Contract):
```powershell
.venv\Scripts\pytest.exe tests -v
```
**Test Results**: **42 passed in 6.06s**

Run complete regression suite including preserved legacy foundation tests:
```powershell
.venv\Scripts\pytest.exe tests docker/tests/test_platform_foundation.py -v
```
**Test Results**: **71 passed in 23.38s (100% passing)**

---

## 10. Documentation Index

- [Architecture Guide](docs/architecture.md): Modular boundaries, domain contracts, and Switch centrality.
- [Infrastructure Discovery Engine](docs/infrastructure-discovery.md): Filesystem protections, parsers, and normalized schema.
- [FinOps Intelligence Engine](docs/finops-engine.md): Pricing catalog, Decimal arithmetic, and financial hygiene rules.
- [Security Rule Catalog](docs/security-rules.md): Complete specifications for rules `SEC-001` through `SEC-010`.
- [Reliability & SRE Analysis](docs/reliability-analysis.md): Complete specifications for rules `REL-001` through `REL-005`.
- [Evidence & Findings Model](docs/evidence-model.md): Schema, confidence scoring, and SQLite persistence.
- [Switch Integration Guide](docs/switch-integration.md): Wire protocol specification, WebSocket streaming, and room setup.
- [Testing Guide](docs/testing.md): Automated testing strategy, test layers, and verification commands.
