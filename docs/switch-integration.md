# CloudPilot SwitchOps — Switch Integration & Protocol Guide

## 1. Official Documentation Consulted

The Switch integration was implemented by querying the official Switch AI documentation Model Context Protocol (MCP) server at `https://docs.switchagents.ai/mcp` and inspecting the following official resources:
- `/switch-rooms/internals/agent-protocol.mdx`: Wire protocol overview, transport, auth, registration.
- `/switch-rooms/internals/agent-connection.mdx`: WebSocket connection, query params, frame types, heartbeat (ping/pong), generation & cursor fencing, eviction codes.
- `/switch-rooms/internals/agent-events.mdx`: Event catalog, message payloads, participant IDs (`@localpart:server`), addressed filter mechanics.
- `/switch-rooms/getting-started/create-a-room.mdx`: Room creation, participant setup, greeting options.

---

## 2. Wire Protocol Specifications

### A. Health Probe
- **Method & Path**: `GET /health`
- **Authentication**: None (public endpoint).
- **Purpose**: Used by clients to verify that the base URL points directly to the Switch Agent Bridge (rather than Gateway or an unintended web host). A 401 indicates that the URL points to the Gateway admin interface, not the bridge.

### B. Out-of-Band Agent Registration
- **Method & Path**: `POST /agents`
- **Authentication**: `Authorization: Bearer <registration_key>` (an API key of type `registration` or bootstrap key).
- **Request Payload**:
  ```json
  {
    "name": "cloudpilot-ops-agent",
    "description": "CloudPilot SwitchOps Autonomous Control Room Agent",
    "connector_type": "custom",
    "integration_profile": {
      "connection_model": "always_on",
      "message_exchange": true,
      "pre_invocation_mediation": [],
      "post_invocation_mediation": [],
      "event_reporting": []
    }
  }
  ```
- **Response**:
  ```json
  {
    "id": "agent-uuid",
    "api_key": "swak-secret-agent-key"
  }
  ```
- *Note*: The agent's `api_key` is returned only once. It authenticates all subsequent WebSocket and HTTP requests made by the agent.

### C. Addressing Permissions
- **Method & Path**: `POST /agents/{agent_id}/ops/update_agent_detail`
- **Authentication**: `Authorization: Bearer <agent_api_key>`
- **Request Payload**:
  ```json
  {
    "agent_id": "<agent_id>",
    "addressing": "owner_and_owner_agents"
  }
  ```
  *(or `"anyone"` depending on deployment policy).*

### D. Outbound Room Messaging
- **Method & Path**: `POST /agents/{agent_id}/message`
- **Authentication**: `Authorization: Bearer <agent_api_key>`
- **Request Payload**:
  ```json
  {
    "room_id": "cloudpilot-ops",
    "content": "### [CloudPilot SwitchOps] Task Execution Report\n- **Status**: COMPLETED..."
  }
  ```
- *Note*: Does not require an active WebSocket connection.

### E. Inbound WebSocket Streaming & Liveness
- **Method & Path**: `GET /agents/{agent_id}/connection/ws`
- **Authentication**: `Authorization: Bearer <agent_api_key>` (passed in handshake headers)
- **Query Parameters**:
  - `connection_id`: Stable UUID chosen by the client and reused across reconnects.
  - `rooms`: Comma-separated room IDs to claim (e.g. `cloudpilot-ops`).
  - `filter`: `addressed` (filters events to only those where `payload.addressed` is `true`).
  - `scope`: `single` (one room) or `all`.
  - `start_from`: `head` or sequence number to resume.
  - `expected_generation`: Generation from last `connection_state` to fence reconnects against takeovers.
- **Protocol Frames**:
  1. `connection_state` (first frame on connection):
     ```json
     {
       "type": "connection_state",
       "connection_id": "...",
       "agent_id": "...",
       "generation": "gen-1",
       "cursor": 100,
       "rooms": ["cloudpilot-ops"]
     }
     ```
  2. `ping` (sent by Switch server every 2 seconds):
     The client **MUST** reply immediately with a pong carrying its highest processed sequence cursor:
     ```json
     {
       "type": "pong",
       "cursor": 100
     }
     ```
     *Lapse timeout*: If client fails to reply within 6 seconds, the server evicts the connection with code `heartbeat_lapsed`.
  3. `event` (incoming room message):
     ```json
     {
       "type": "event",
       "sequence": 101,
       "event": "message",
       "payload": {
         "addressed": true,
         "sender": "@operator:switch",
         "sender_name": "Human Operator",
         "message_id": "msg-001",
         "body": "@cloudpilot-ops-agent assess ./samples/staging for cost, security and reliability risks. Read-only assessment.",
         "timestamp": 1730000000000
       }
     }
     ```
  4. `evicted`: Notifies client that its connection was terminated (`taken_over`, `heartbeat_lapsed`, etc.).

---

## 3. Configuring the Switch Room (`cloudpilot-ops`)

### Step 1: Open Switch Console or Gateway
- Start Switch Console on your machine, or navigate to the Switch Gateway administrative surface (typically `http://localhost:8080/gateway`).

### Step 2: Create the Operations Room
- In the Switch Console or Gateway sidebar, select **Rooms** > **Create Room**.
- **Room Name**: `cloudpilot-ops`
- **Topic**: `CloudPilot Autonomous Cloud Operations Control Room`
- **Room Instructions**:
  ```text
  You are collaborating with CloudPilot SwitchOps to review cloud infrastructure,
  diagnose billing anomalies, and manage change approvals.
  Always enforce least-privilege read-only defaults. Never perform unapproved changes.
  ```

### Step 3: Add Agent to Room
- Add `@cloudpilot-ops-agent` to `cloudpilot-ops`.
- Ensure the agent's addressing policy allows human operators to address it.

---

## 4. Smoke Test Procedure

### Automated Protocol Contract Tests
The repository includes automated contract tests verifying the exact Switch wire protocol:
```powershell
.venv\Scripts\pytest.exe tests/contract/test_switch_protocol_contract.py -v
.venv\Scripts\pytest.exe tests/contract/test_switch_websocket_wire.py -v
```

### End-to-End Live Verification in Switch Room
1. Ensure Switch Console / Docker is running with the Agent Bridge active on `http://localhost:8080`.
2. Configure `.env` with:
   ```env
   CLOUDPILOT_SWITCH_BRIDGE_URL="http://localhost:8080"
   CLOUDPILOT_SWITCH_ROOM_ID="cloudpilot-ops"
   CLOUDPILOT_SWITCH_AGENT_ID="<your-agent-id>"
   CLOUDPILOT_SWITCH_AGENT_API_KEY="<your-agent-api-key>"
   ```
3. Start CloudPilot SwitchOps:
   ```powershell
   .venv\Scripts\uvicorn.exe app.main:app --port 8000
   ```
4. In the `cloudpilot-ops` room, trigger a Phase 2 autonomous assessment:
   ```text
   @cloudpilot-ops-agent assess ./samples/staging for cost, security and reliability risks. Read-only assessment. Do not modify anything.
   ```
5. **Expected Message Sequence in Room**:
   - **Message 1 (Acknowledgment)**:
     ```text
     [CloudPilot SwitchOps] Acknowledged request: Task from Platform Engineer: @cloudpilot-ops-agent assess...
     - Task ID: task-...
     - Status: ACKNOWLEDGED
     ```
   - **Message 2 (Discovery Initiation)**:
     ```text
     🔍 Starting Infrastructure Discovery
     - Target Workspace: ./samples/staging
     - Mode: Read-only assessment (zero modifications)
     Scanning for Terraform (*.tf) and Docker Compose definitions...
     ```
   - **Message 3 (Discovery Completed)**:
     ```text
     📦 Infrastructure Discovery Completed
     - Discovered Files: 2 (main.tf, docker-compose.yml)
     - Total Resources: 9
     - Scan Duration: 29.1ms
     Dispatching specialist agents: finops-specialist, secops-specialist...
     ```
   - **Message 4 (FinOps Specialist Report)**:
     ```text
     💰 FinOps Intelligence Report (finops-specialist)
     - Estimated Monthly Baseline: $212.83 USD
     - Billable Components Evaluated: 6
     - Financial Hygiene Findings: 4
     Key Cost Drivers & Sizing:
       • staging_postgres (aws_db_instance:db.m5.large): $99.28/mo
       • staging_web (aws_instance:m5.large): $70.08/mo
     ```
   - **Message 5 (SecOps Specialist Report)**:
     ```text
     🛡️ SecOps & SRE Audit Report (secops-specialist)
     - Security Findings: 10
     - Reliability Deficits: 5
     - Severity Breakdown: 🚨 4 Critical | ⚠️ 4 High | ℹ️ 3 Med | 📋 4 Low
     ```
   - **Message 6 (Consolidated Assessment Report)**:
     ```text
     ## 📊 [CloudPilot SwitchOps] Task Execution Report — Consolidated Assessment
     - Task ID: task-... | Status: COMPLETED
     - Target Workspace: ./samples/staging
     - Total Discovered Resources: 9
     - Estimated Monthly Baseline: $212.83 USD
     - Total Findings: 18
     ```
6. Query assessment data via API:
   ```powershell
   curl http://localhost:8000/api/v1/assessments/<task_id>
   curl http://localhost:8000/api/v1/assessments/<task_id>/findings
   curl http://localhost:8000/api/v1/assessments/<task_id>/cost-breakdown
   ```
