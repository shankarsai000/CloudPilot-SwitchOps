# CloudPilot SwitchOps — Phase 4.3 Live Switch Integration & Wire Protocol Specification

**Project:** CloudPilot SwitchOps  
**Document:** Live Switch Integration Specification & Verification  
**Release Target:** `v4.3.0-submission-ready`  
**Evaluation Track:** Flip the Switch — Track 01: Best Business Workflow  

---

## 1. Executive Overview

CloudPilot SwitchOps integrates with the Switch collaboration environment using the native **Switch Agent Bridge Protocol**. Switch serves as the human-in-the-loop control room where cloud architects, FinOps leads, and SecOps specialists interact with CloudPilot agents to inspect infrastructure, review Pareto-optimal optimization proposals, and authorize safe, bounded changes.

The integration architecture implements a dual-mode communication model:
1. **Inbound Event Stream (WebSocket):** Real-time bi-directional connection receiving user messages, operator approvals, room commands, and status queries.
2. **Outbound Notification Channel (HTTP REST):** Structured, high-integrity message publication to designated Switch collaboration rooms.
3. **Truthful Fallback Engine (Emulated Bridge):** When external Switch bridge credentials or live network endpoints are unavailable, the system operates seamlessly in deterministic emulated mode without misrepresenting mock operations as live cloud events.

---

## 2. Wire Protocol Specification

```
+-------------------------------------------------------------------------+
|                              SWITCH PLATFORM                            |
|                                                                         |
|  +---------------------------+        +------------------------------+  |
|  |   Switch Room: ops-room   |        | Switch Agent Bridge Service  |  |
|  |  (Human Operators & SRE)  |        |    (ws:// and http://)       |  |
|  +-------------+-------------+        +---------------+--------------+  |
|                ^                                      ^                 |
+----------------|--------------------------------------|-----------------+
                 | HTTP POST (Messages & Proposals)     | WebSocket (Inbound Events)
                 |                                      |
+----------------v--------------------------------------v-----------------+
|                       CLOUDPILOT SWITCHOPS CORE                         |
|                                                                         |
|  +---------------------------+        +------------------------------+  |
|  |  SwitchWireClient (REST)  |        |  SwitchConnectionManager (WS)|  |
|  +---------------------------+        +------------------------------+  |
|                |                                      |                 |
|                +------------------+-------------------+                 |
|                                   v                                     |
|                       SwitchEventHandler / TaskService                  |
+-------------------------------------------------------------------------+
```

### 2.1 Outbound REST API Contract

- **Endpoint:** `POST {switch_bridge_url}/rooms/{room_id}/messages`
- **Headers:**
  - `Content-Type: application/json`
  - `Authorization: Bearer {switch_agent_api_key}`
  - `X-Switch-Agent-Id: {agent_id}`
  - `X-Correlation-ID: {correlation_id}`
- **Payload Schema:**
  ```json
  {
    "sender_id": "cloudpilot-agent",
    "sender_role": "agent",
    "content": "Proposal prop-9a4f2 ready for review. Estimated savings: $148.50/mo. SHA-256: 4f8a...",
    "metadata": {
      "type": "PROPOSAL_PENDING_APPROVAL",
      "proposal_id": "prop-9a4f2",
      "proposal_hash": "4f8a7c2b3e5d...",
      "task_id": "task-01",
      "estimated_monthly_savings_usd": 148.50,
      "risk_level": "LOW",
      "review_url": "http://localhost:8000/dashboard#approval-center"
    }
  }
  ```

### 2.2 Inbound WebSocket Contract

- **Endpoint:** `GET {switch_bridge_ws_url}/agents/{agent_id}/connection/ws`
- **Handshake Protocol:**
  - Standard WebSocket Upgrade (`HTTP/1.1 101 Switching Protocols`)
  - Subprotocol: `switch.agent.v1`
  - Handshake Query: `?token={switch_agent_api_key}&room={room_id}`
- **Inbound Event Schema (e.g. In-Room Approval):**
  ```json
  {
    "event_id": "evt-771829",
    "room_id": "ops-room",
    "sender": {
      "id": "usr-sarah-arch",
      "name": "Sarah Connor",
      "role": "cloud-architect"
    },
    "event_type": "ROOM_COMMAND",
    "command": "APPROVE",
    "payload": {
      "proposal_id": "prop-9a4f2",
      "token": "tok_signed_sha256_e4c8...",
      "reason": "Approved during architecture review for staging cost optimization."
    },
    "timestamp": "2026-11-06T14:40:00Z"
  }
  ```

---

## 3. Connection Lifecycle and Health States

The `SwitchConnectionManager` manages connection states with exponential backoff and jitter:

```
[INIT] ---> [CONNECTING] ---> [CONNECTED] ---> [LISTENING]
                  |                 |
                  | (Fail)          | (Socket Dropped)
                  v                 v
            [LIVE_UNVERIFIED]   [RECONNECTING]
                  |                 |
                  | (Retry Limit)   | (Max Retries)
                  v                 v
          [FALLBACK_EMULATED] <-----+
```

| State | Health Probe (`GET /health/switch`) | Operational Behavior |
| :--- | :--- | :--- |
| `CONNECTED` | `status: "connected", mode: "live"` | Full bi-directional streaming with active Switch room. |
| `CONNECTING` | `status: "connecting", mode: "live"` | Establishing WebSocket handshake with remote bridge. |
| `RECONNECTING` | `status: "reconnecting", mode: "live"` | Backoff retry after network interruption. Outbound queue buffered. |
| `LIVE_UNVERIFIED` | `status: "unverified", mode: "live"` | Live bridge URL configured but remote server unreachable or credentials unverified. |
| `EMULATED_MODE` | `status: "ok", mode: "emulated"` | Deterministic in-memory bridge active. Safe local operation for development and isolated testing. |

---

## 4. Truthfulness and External Dependency Disclosure

In accordance with CloudPilot core engineering ethics:
1. When running without external Switch bridge infrastructure, CloudPilot explicitly reports its state as `EMULATED_MODE` (or `LIVE_UNVERIFIED` when live mode was requested without a responsive bridge).
2. The platform never fakes network responses or fabricates external server confirmation.
3. If external Switch room infrastructure is unavailable during evaluation, the platform is classified as **`SUBMISSION_READY_WITH_DOCUMENTED_EXTERNAL_LIMITATION`**.

To test against a live external Switch bridge:
```bash
export SWITCH_MODE=live
export SWITCH_BRIDGE_URL=https://bridge.switch.network
export SWITCH_AGENT_API_KEY=sw_live_sec_prod_...
export SWITCH_ROOM_ID=production-cloudops
python -m app.main
```
