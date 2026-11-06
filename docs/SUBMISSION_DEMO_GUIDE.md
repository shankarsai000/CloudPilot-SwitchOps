# CloudPilot SwitchOps — Judge & Reviewer Evaluation Guide

**Project:** CloudPilot SwitchOps  
**Track:** Flip the Switch — Track 01: Best Business Workflow  
**Release Tag:** `v4.3.1-release-integrity`  
**Estimated Review Time:** ~5–7 minutes  

---

## 1. Quick Verification (30 Seconds)

To verify the complete test suite:

```bash
# Windows:
.\.venv\Scripts\pytest.exe tests docker/tests/test_platform_foundation.py -q

# Linux/macOS:
# pytest tests docker/tests/test_platform_foundation.py -q
```
**Expected Output:** `249 passed in ~28s`

---

## 2. Interactive CLI Demonstrations (2 Minutes)

CloudPilot provides separate, transparent automated demonstration scripts tailored for both offline evaluation and live Switch environments:

### 2.1 Offline Emulated Golden Path Workflow Demonstration
```bash
python scripts/demo_submission_offline.py
# (or: python scripts/demo_submission.py)
```
**What this demonstrates (Mode: OFFLINE EMULATION with `EmulatedSwitchBridge`):**
1. Connects to Switch wire adapter in verified `EMULATED_MODE`.
2. Ingests optimization prompt from in-room platform lead: `@platform-lead:switch`.
3. Discovers infrastructure in `samples/staging` (Terraform HCL + Docker Compose).
4. Normalizes 9 resources and maps cross-provider dependencies.
5. Emits FinOps pricing analysis ($232.29 baseline spend, $54.90/mo potential savings with offline catalog disclosure).
6. Runs SecOps and SRE deterministic rule evaluations (30 findings detected).
7. Evaluates 74 candidate actions across Cost, Risk, Reliability, and Effort.
8. **Formally proves hard invariants using Z3 Theorem Prover (`Z3_CONSTRAINTS_SAT`)**.
9. Computes 15 Pareto optimal plans and selects recommended plan.
10. Generates change proposal locked by pre-mutation SHA-256 hash.
11. **Publishes proposal notification directly to the Switch collaboration room and asserts delivery.**
12. **Dynamically evaluates all 14 points of the human governance review checklist against real persisted models.**
13. Simulates in-room human approval by `@platform-lead:switch`.
14. Issues single-use HMAC-SHA256 signed approval token.
15. Copies target files to an **isolated sandbox workspace** (zero live cloud mutation).
16. Applies bounded AST attribute mutations (`instance_type` and KMS encryption).
17. Re-parses AST independently to verify 100% valid HCL/YAML syntax.
18. **Publishes verified outcome back to Switch room (asserts delivery) and persists complete SQLite audit trail.**

### 2.2 Strict Live Switch Workflow Demonstration
```bash
python scripts/demo_submission_live.py
```
**What this demonstrates (Mode: STRICT LIVE `SwitchWireClient`):**
- **Strict Network Path:** Strictly uses HTTP REST and WebSocket wire connections against an external Switch bridge.
- **Fail-Closed on Unmet Dependencies:** If live bridge credentials (`SWITCH_AGENT_API_KEY`) or live bridge connectivity are absent, it **never falls back to emulation or fake data**. Instead, it clearly prints `BLOCKED_EXTERNAL_DEPENDENCY` and exits cleanly with exit code `2`.
- **Live Operation:** When valid live credentials and bridge are active, executes `verify_auth()`, sends live room messages, awaits operator approval, executes bounded changes, and publishes verified outcomes.

### 2.3 Negative Adversarial & Safety Gates Demonstration
```bash
python scripts/demo_submission_negative.py
```
**What this demonstrates:**
- **Gate 1:** In-room human rejection halts workflow immediately; zero mutations occur (`REJECTED`).
- **Gate 2:** Caller-supplied role escalation by unauthorized user (`@intruder:switch`) is rejected fail-closed (`UNAUTHORIZED_APPROVER_ROLE`).
- **Gate 3:** Out-of-band file tampering causes pre-mutation SHA-256 mismatch, immediately aborting execution (`HashMismatchError`).
- **Gate 4:** Replay attack with consumed approval token is blocked fail-closed; execution count remains strictly 1.
- **Gate 5:** Air-gapped boundary verified: zero live cloud calls (`terraform apply`), sample files remain untouched.

---

## 3. Interactive Web Dashboard Tour (3 Minutes)

### 3.1 Start the Server
```bash
python -m app.main
```
Open your browser to:
```
http://localhost:8000/dashboard
```

### 3.2 Tour of the 7 Operational Areas

1. **Cockpit Overview (Screen 0):**
   - Click the green **"▶ Run Assessment & Decision"** button in the header.
   - Watch the KPI cards update in real time: Discovered Resources, Estimated Waste/Savings, SecOps/SRE findings, and Z3 Formal Solvability.
2. **Area A: Infrastructure Overview:**
   - Click "Area A: Infrastructure" on the sidebar.
   - Inspect the table of discovered Terraform and Docker Compose resources parsed from `samples/staging`.
3. **Area B: Specialist Analysis:**
   - Click "Area B: Specialists".
   - Review the three specialist panels: FinOps Intelligence (with offline catalog disclaimer), SecOps Posture (severity breakdowns), and SRE Reliability.
4. **Area C: Decision Intelligence & Z3 Solver:**
   - Click "Area C: Decisions & Z3".
   - Inspect the formal Z3 solver verification badge (`Z3_CONSTRAINTS_SAT`) and the multi-objective Pareto frontier table.
5. **Area D: Human Approval Center:**
   - Click "Area D: Approval Center".
   - Inspect the active proposal: Proposal ID, locked SHA-256 hash, diff preview, and the 14-point review checklist.
   - Test human-in-the-loop actions: Click **"✔ Approve Change"** as `PLATFORM_LEAD`. Notice the token signed and status updated to `APPROVED`.
   - Switch operator in the top dropdown to `guest-viewer:VIEWER` and attempt an action to observe fail-closed RBAC rejection.
6. **Area E: Sandbox Execution:**
   - Click "Area E: Sandbox Execution".
   - Click **"⚡ Execute Approved Proposal"**.
   - Watch the live execution console: isolated temporary sandbox path, pre-mutation hash, post-mutation hash, and independent syntactic verification status.
7. **Area F: Switch Collaboration:**
   - Click "Area F: Switch Collab".
   - Inspect the connection telemetry: Bridge URL, Switch Room ID (`cloudpilot-ops-room`), Wire Protocol (WebSocket + REST), and truthful mode badge (`EMULATED`).
   - View the live stream of messages published to the room.
8. **Area G: Correlated Audit Trail:**
   - Click "Area G: Correlated Audit".
   - Trace the complete end-to-end lineage linking Task ID -> Decision ID -> Proposal ID -> Approval Token -> Execution Record.

---

## 4. Verification with a Live External Switch Bridge

If you have a live Switch Agent Bridge running:

```bash
export SWITCH_MODE=live
export SWITCH_BRIDGE_URL=https://your-switch-bridge-host
export SWITCH_AGENT_API_KEY=your-live-agent-key
export SWITCH_ROOM_ID=cloudpilot-ops
export SWITCH_AGENT_ID=cloudpilot-ops-agent
export SWITCH_REGISTRATION_KEY=your-registration-secret

# Test live connection via the strict live CLI script:
python scripts/demo_submission_live.py

# Or start the server:
python -m app.main
```

Query the health endpoint:
```bash
curl http://localhost:8000/health/switch
```
The response will reflect:
```json
{
  "status": "connected",
  "mode": "live",
  "bridge_url": "https://your-switch-bridge-host",
  "room_id": "cloudpilot-ops",
  "connected": true,
  "message": "Authenticated live Switch bridge connected."
}
```
*(Note: Placeholder tokens such as `<your-key>`, `dummy`, or `test` are strictly rejected by the config validator, preventing unauthenticated live status).*

