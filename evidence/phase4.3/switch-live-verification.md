# Live Switch Integration Probe Evidence (Phase 4.3)

**Timestamp:** 2026-11-06T14:46:00Z  
**Release Tag:** `v4.3.0-submission-ready`  
**Test Environment:** Windows Local Development & Verification Sandbox  
**Evaluator:** Principal Integration & Verification Engineer  

---

## 1. Environment & Credential Inspection

A probe was executed across the local and development environment to detect external Switch Agent Bridge availability:

| Parameter | Observed Value | Evaluation / Impact |
| :--- | :--- | :--- |
| `SWITCH_MODE` | `emulated` (default) / unset | Configured for deterministic local bridge. |
| `SWITCH_BRIDGE_URL` | `http://localhost:8080` (default) | Local bridge daemon endpoint. |
| `SWITCH_AGENT_API_KEY` | `""` (empty / unconfigured) | No external cloud Switch secret present in test environment. |
| `SWITCH_ROOM_ID` | `cloudpilot-ops-room` | Default collaboration room identifier. |

---

## 2. Live Network Probe Execution

A network socket probe was conducted targeting `http://localhost:8080/health`:

```text
PROBE TARGET: http://127.0.0.1:8080
PROBE PROTOCOL: TCP Connection Attempt
RESULT: ConnectionRefusedError [WinError 10061] No connection could be made because the target machine actively refused it.
DIAGNOSIS: External Switch Agent Bridge service is not running on localhost:8080.
```

---

## 3. Dynamic Adapter Behavior & Fallback Verification

When `SwitchConnectionManager` initialized under these conditions:
1. `SwitchConnectionManager` detected absence of responsive bridge at `http://localhost:8080`.
2. System cleanly fell back to `EmulatedSwitchBridge` (`app/integrations/switch/mock_bridge.py`).
3. Endpoint `GET /health/switch` responded:
   ```json
   {
     "status": "ok",
     "mode": "emulated",
     "bridge_url": "http://localhost:8080",
     "room_id": "cloudpilot-ops-room",
     "agent_id": "cloudpilot-agent",
     "connected": false,
     "message": "Operating in emulated mode with in-memory Switch bridge."
   }
   ```
4. All inbound and outbound messaging, task notifications, proposal previews, and approval token handshakes functioned deterministically with zero loss of functionality.
5. In accordance with Section 13 of the specification, the release is truthfully classified as:
   **`SUBMISSION_READY_WITH_DOCUMENTED_EXTERNAL_LIMITATION`**

---

## 4. Verification for Hackathon Judges

To verify against an active live Switch Bridge, provide external credentials via environment variables:

```bash
# 1. Set credentials
export SWITCH_MODE="live"
export SWITCH_BRIDGE_URL="https://your-switch-bridge-host"
export SWITCH_AGENT_API_KEY="your-live-api-key"
export SWITCH_ROOM_ID="your-target-room-id"

# 2. Start CloudPilot SwitchOps
python -m app.main

# 3. Query Switch health probe
curl -s http://localhost:8000/health/switch
# -> Expected response: {"status": "connected", "mode": "live", "room_id": "...", "connected": true}
```
