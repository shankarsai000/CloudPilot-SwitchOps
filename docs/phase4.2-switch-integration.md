# CloudPilot SwitchOps — Phase 4.2 Switch Integration Specification
## Wire Protocol Reference, Connection Management & Resilience

---

## 1. Switch Agent Bridge Protocol Overview

The Switch Agent Bridge provides an agent-first integration boundary connecting AI agents with human collaboration rooms. CloudPilot SwitchOps implements the **Switch Wire Protocol (v1)** using an asymmetric transport architecture:

- **Inbound Streaming:** Long-lived WebSocket connection (`GET /agents/{id}/connection/ws`) ingesting addressed chat messages, heartbeats, and room participant events.
- **Outbound Publishing:** Idempotent REST API requests (`POST /rooms/{room_id}/messages`) publishing markdown reports, structured proposals, and execution verification outcomes.

---

## 2. Wire Protocol Frame Specification

Incoming WebSocket frames conform to the canonical JSON dictionary envelope:

```json
{
  "type": "event",
  "sequence": 42,
  "event": "message",
  "metadata": {
    "authorization": "Bearer ...",
    "user_role": "PLATFORM_LEAD"
  },
  "payload": {
    "message_id": "msg-8f12a4b9",
    "sender": "@platform-lead:switch",
    "sender_name": "Lead Platform Architect",
    "addressed": true,
    "body": "@cloudpilot-ops-agent approve proposal prop-5dc90a7f55",
    "timestamp": 1730900000000,
    "thread_id": null,
    "attachments": []
  }
}
```

### Supported Frame Types

1. `connection_state`: Handshake acknowledging agent session registration and cursor fence.
2. `ping` / `pong`: Bidirectional keep-alive frame exchange every 2.0 seconds.
3. `event`: Dispatched room events containing chat messages or participant updates.
4. `evicted`: Notifies agent of session preemption by a newer generation instance.

---

## 3. Resilience, Retries & Deduplication

### 3.1 Bounded Exponential Backoff with Jitter

When communicating with the Switch Bridge over HTTP or establishing WebSocket sessions, `SwitchConnectionManager` enforces bounded exponential backoff with randomized jitter to prevent thundering herd conditions:

$$\text{delay} = \min\left(30.0, \text{base\_delay} \times 2^{\text{attempt}} + \text{jitter}\right)$$

Where:
- $\text{base\_delay} = 1.0\text{s}$ (configurable via `SWITCH_RETRY_BASE_DELAY`)
- $\text{max\_delay} = 8.0\text{s}$ (configurable via `SWITCH_RETRY_MAX_DELAY`)
- $\text{max\_retries} = 3$ (configurable via `SWITCH_MAX_RETRIES`)
- $\text{jitter} \in [0.0, \min(0.25, \text{base\_delay} \times 0.5)]$

### 3.2 Inbound Message Deduplication

Switch at-least-once message delivery guarantees can result in redelivered message frames. `SwitchConnectionManager.is_duplicate_inbound_event()` tracks processed message IDs and strictly monotonically increasing sequence cursors to discard redundant dispatches.

### 3.3 Outbound Publication Idempotency

Every outbound collaboration message is assigned a deterministic 24-character SHA-256 idempotency key:

$$\text{key} = \text{SHA256}\left(\text{task\_id} : \text{event\_type} : \text{decision\_id} : \text{proposal\_id} : \text{execution\_id} : \text{correlation\_id} : \text{summary\_hash}\right)_{[0:24]}$$

Duplicate outbound calls referencing an already-published key retrieve cached delivery metadata rather than posting duplicate messages to the Switch room.

### 3.4 Disconnection Outbox Queue

If the Switch Bridge becomes temporarily unreachable after CloudPilot has executed a local mutation, the event is not lost. The message is serialized to the `_pending_outbox` queue with status `PENDING_RETRY`. Once network connectivity is restored, `flush_pending_outbox()` flushes all queued records without duplicate publications.

---

## 4. Operational Diagnostics API

CloudPilot exposes real-time Switch connectivity and capabilities via:
- `GET /health/switch`
- `GET /api/v1/switch/status` (API alias)

### Sample Diagnostic Response

```json
{
  "configured": true,
  "state": "EMULATED_MODE",
  "healthy": true,
  "truthful_report": {
    "state": "EMULATED_MODE",
    "connection_state": "EMULATED_MODE",
    "integration_mode": "EMULATED",
    "verified_live": false,
    "bridge_url": "mock://switch-bridge",
    "room_id": "cloudpilot-ops",
    "agent_id": "cloudpilot-ops-agent",
    "session_id": "swsess-831a7a1f2c",
    "cursor": 12,
    "last_successful_communication": "2026-11-06T14:26:46.304701Z",
    "external_blocker": null,
    "retry_count": 0,
    "latency_ms": 1.25,
    "messages_published_count": 4,
    "events_received_count": 2,
    "protocol_capabilities": {
      "protocol_version": "switch-wire-v1",
      "transport": "websocket_in_http_out",
      "supports_health_probe": true,
      "supports_agent_registration": true,
      "supports_room_message_post": true,
      "supports_websocket_streaming": true,
      "supports_heartbeat_cursor_fencing": true,
      "supports_native_approval_buttons": false,
      "approval_mechanism": "correlated_command_and_authenticated_rest_api"
    }
  },
  "capabilities": {
    "protocol_version": "switch-wire-v1",
    "transport": "websocket_in_http_out",
    "approval_mechanism": "correlated_command_and_authenticated_rest_api"
  },
  "timestamp": "2026-11-06T14:27:00.000000Z"
}
```
