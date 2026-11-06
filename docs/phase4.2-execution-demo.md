# CloudPilot SwitchOps — Phase 4.2 Demonstration Guide
## End-to-End Walkthrough of the Verified Switch Operations Workflow

---

## 1. Demonstration Scenario Setup

CloudPilot SwitchOps Phase 4.2 provides a dedicated synthetic infrastructure scenario located at:
`samples/phase4_2_demo/infrastructure/`

The scenario defines realistic staging compute infrastructure:
- **File:** `samples/phase4_2_demo/infrastructure/main.tf`
- **Resource:** `aws_instance.demo_web_service`
- **Initial Configuration:** `instance_type = "m5.large"` ($70.08/mo USD baseline)
- **Target Optimization:** Rightsize to `instance_type = "t3.small"` ($15.18/mo USD, saving $54.90/mo USD)
- **Hard Constraints:** Preservation of provider block, tags (`ManagedBy = "CloudPilot-SwitchOps"`), and AMI references.

---

## 2. Positive 10-Step Workflow Execution

Run the positive demonstration script:

```powershell
python scripts/demo_phase4_2.py
```

### Script Output Breakdown

````carousel
<!-- slide -->
#### Step 1: Health Probe & Capability Negotiation
```text
--- [STEP 1/10] Verify Switch Integration & Capabilities ---
  Connection State:      EMULATED_MODE
  Operational:           True
  Wire Protocol:         switch-wire-v1
  Transport:             websocket_in_http_out
  Approval Mechanism:    correlated_command_and_authenticated_rest_api
  Truthful Notice:       Operating in EMULATED_MODE (air-gapped local emulation).
```
<!-- slide -->
#### Steps 2–4: Ingestion, Multi-Specialist Discovery & SMT Decision Engine
```text
--- [STEP 2/10] Receive Optimization Request in Switch Collaboration Room ---
  Inbound Room Event:
    Room:        cloudpilot-ops
    Sender:      @platform-lead:switch (Lead Platform Architect)
    Prompt:      @cloudpilot-ops-agent decide on staging infrastructure optimization...
  Task Created:          task-831a7a1f2c5a (Correlation: corr-d2823261e631)

--- [STEP 3/10] Infrastructure Discovery & Multi-Specialist Assessment ---
  Discovered Resources:  1
    • res-aws-aws_instance.demo_web_service (aws_instance) in main.tf
  Monthly Baseline Cost: $70.08 USD

--- [STEP 4/10] Decision Intelligence, SMT Verification & Pareto Optimization ---
  Decision ID:           dec-7ee1fe61ca
  Z3 Solver Status:      Z3_CONSTRAINTS_SAT
  Candidates Evaluated:  1 generated, 1 feasible
  Selected Action:       Rightsize EC2 'demo_web_service' from m5.large to t3.small
    - Baseline:          $70.08/mo -> Projected: $15.18/mo
    - Monthly Savings:   $54.90/mo USD
```
<!-- slide -->
#### Steps 5–7: Proposal Publication, Approval & Isolated Execution
```text
--- [STEP 5/10] Publish 14-Point Infrastructure Change Proposal in Switch Room ---
  Proposal ID:           prop-39f6e0e6e5
  Proposal SHA-256 Hash: ae324a91379892d92dd6ebdd297cf9590d37cc388b0abb4213b8b9eb5d20ac98
  Proposal Status:       PENDING_APPROVAL

--- [STEP 6/10] Authenticated Human Authorization in Switch Room ---
  Approver:              @platform-lead:switch (Directory Role: PLATFORM_LEAD)
  Command:               @cloudpilot-ops-agent approve proposal prop-39f6e0e6e5
  Token Issued:          tok-11539451dd3fc2b3 (Single-use HMAC bound)

--- [STEP 7/10] Execute Bounded Mutations in Isolated Workspace Sandbox ---
  Execution ID:          exec-2bbd0ab47b
  Workspace Sandbox:     D:\CloudPilot AI\.cloudpilot\workspaces\exec-2bbd0ab47b
  Applied Mutations:     1 file(s)
    • main.tf: SHA256 before=f96d51b85ba5f6a6... after=a78ff9b0c91b0e5c...
```
<!-- slide -->
#### Steps 8–10: Post-Verification, Room Delivery & Correlated Audit Trace
```text
--- [STEP 8/10] Independent Post-Execution Syntactic & Hash Verification ---
  Syntactic Check:       HCL syntax verification PASSED
  Cryptographic Hash:    Expected after-state digests MATCH actual mutated file digests
  Disallowed Write APIs: ZERO terraform apply / Live cloud mutations executed

--- [STEP 9/10] Publish Outcome Notification to Switch Room ---
  Outcome Message ID:    msg-b4d81bc0
  Status:                COMPLETED

--- [STEP 10/10] Correlated Audit Trail & Evidence Preservation ---
  Collaboration Events:  11 audit events recorded
  Correlated Trace:
    Task ID:             task-831a7a1f2c5a
    Correlation ID:      corr-d2823261e631
    Decision ID:         dec-7ee1fe61ca
    Proposal ID:         prop-39f6e0e6e5
    Approval ID:         appr-2cefcd1710
    Execution ID:        exec-2bbd0ab47b
```
````

---

## 3. Negative Safety Demonstrations

To verify that fail-closed safety controls operate effectively, run:

```powershell
python scripts/demo_phase4_2_negative.py
```

### Safety Gates Verified:
1. **Gate 1: Human In-Room Rejection**
   - `@cloudpilot-ops-agent reject proposal <id> reason: ...`
   - Halts workflow, moves proposal to `REJECTED`, and confirms 0 mutations occur.
2. **Gate 2: Untrusted Role Escalation Fails Closed**
   - `@intruder:switch` attempts approval with claimed role `PLATFORM_LEAD`.
   - Denied fail-closed with `UNAUTHORIZED_APPROVER_ROLE`; proposal remains pending.
3. **Gate 3: Live Cloud Mutation Prohibition**
   - Live cloud write APIs, `terraform apply`, and external network writes are strictly blocked.
