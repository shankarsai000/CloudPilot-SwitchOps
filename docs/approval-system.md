# CloudPilot SwitchOps — Human Approval System

---

## 1. Overview & Guiding Principle

CloudPilot SwitchOps enforces strict human-in-the-loop governance for all infrastructure actions:

> **No modification can be planned or executed without an authorized human principal issuing a verifiable approval token bound to an immutable proposal hash.**

---

## 2. Role-Based Access Control (RBAC) Matrix

Approvals are gated by cryptographically verified principals possessing specific organizational roles:

| Role Name | Identifier | Can Generate Proposals | Can Issue Approval Tokens | Can Approve Changes | Can Reject Changes | Can Execute Changes |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Platform Lead** | `PLATFORM_LEAD` | Yes | **Yes** | **Yes** | **Yes** | **Yes** |
| **Security Lead** | `SECURITY_LEAD` | Yes | **Yes** | **Yes** | **Yes** | **Yes** |
| **FinOps Lead** | `FINOPS_LEAD` | Yes | **Yes** | **Yes** | **Yes** | **Yes** |
| **Operator** | `OPERATOR` | Yes | No (403) | No (403) | **Yes** | No (403) |
| **Developer** | `DEVELOPER` | Yes | No (403) | No (403) | **Yes** | No (403) |
| **Viewer** | `VIEWER` | Read-only | No (403) | No (403) | No (403) | No (403) |

Any request to issue an approval token or approve a change submitted with an unauthorized role (e.g. `OPERATOR`) is rejected fail-closed with HTTP `403 Forbidden`.

---

## 3. Cryptographic Token Architecture

Approval tokens are generated using HMAC-SHA256 and follow the structured canonical wire format:

$$\text{Token} = \texttt{v1}.\langle\text{proposal\_id}\rangle.\langle\text{nonce}\rangle.\langle\text{timestamp}\rangle.\langle\text{hmac\_signature}\rangle$$

Where:
- `v1`: Protocol format version.
- `proposal_id`: Unique identifier of the approved proposal (e.g., `prop-9fa3a0f653`).
- `nonce`: A 16-byte random hex string ensuring per-token uniqueness.
- `timestamp`: UTC epoch integer representing issuance time.
- `hmac_signature`: Hex digest of HMAC-SHA256 computed across `v1.<proposal_id>.<approver_id>.<nonce>.<timestamp>` using the server secret key.

### Token Verification Invariants
1. **Constant-Time Comparison**: Signatures are checked using `hmac.compare_digest` to prevent timing side-channel attacks.
2. **Proposal Invariance**: Tokens cannot be transferred to any proposal other than the one specified at creation.
3. **Approver Binding**: The token payload encodes the approver ID; verification rejects mismatching principals.
4. **Time-To-Live (TTL)**: Tokens expire automatically after their TTL window (default 3600 seconds).
5. **Replay Protection**: When a token is submitted during approval or execution, its nonce is consumed and stored in memory/database. Resubmission of an already-consumed token is rejected with `TokenAlreadyConsumedError`.

---

## 4. REST API Endpoints

### 4.1 Create Proposal from Decision Run
- **Route**: `POST /api/v1/proposals`
- **Request Body**:
  ```json
  {
    "decision_id": "dec-e15837f8dc",
    "workspace_root": "samples/staging",
    "ttl_seconds": 7200
  }
  ```
- **Response**: `200 OK` with full `Proposal` JSON including `before_state_file_hashes`, `expected_after_state_file_hashes`, and `proposal_hash`.

### 4.2 Query Proposals
- **Route**: `GET /api/v1/proposals`
- **Query Params**: `decision_id`, `status`
- **Route**: `GET /api/v1/proposals/{proposal_id}`

### 4.3 Request Approval Token
- **Route**: `POST /api/v1/approvals/{proposal_id}/token`
- **Headers**:
  - `x-user-id`: Approver identity (e.g. `lead-platform`)
  - `x-user-role`: Approver role (`PLATFORM_LEAD`, `SECURITY_LEAD`, or `FINOPS_LEAD`)
- **Request Body**: `{"ttl_seconds": 3600}`
- **Response**: `200 OK`
  ```json
  {
    "proposal_id": "prop-03b1133ced",
    "approver_id": "lead-platform",
    "approver_role": "PLATFORM_LEAD",
    "token": "v1.prop-03b1133ced.4b684cb84803.1762364373.916e78ba7a54b9d0...",
    "expires_at": "2026-11-05T18:39:33.887912Z"
  }
  ```

### 4.4 Submit Human Approval
- **Route**: `POST /api/v1/approvals/{proposal_id}/approve`
- **Headers**: `x-user-id`, `x-user-role`
- **Request Body**: `{"token": "<token_string>"}`
- **Response**: `200 OK` with `ApprovalRecord`. Transitions proposal status to `APPROVED`.

### 4.5 Submit Human Rejection
- **Route**: `POST /api/v1/approvals/{proposal_id}/reject`
- **Headers**: `x-user-id`, `x-user-role`
- **Request Body**: `{"reason": "Budget review needed"}`
- **Response**: `200 OK` with `ApprovalRecord` marked `REJECTED`. Transitions proposal status to `REJECTED`.

---

## 5. Switch-Native Approval Commands

CloudPilot SwitchOps integrates with Switch team-chat rooms (`cloudpilot-ops`), allowing authorized engineers to review and approve proposals directly within the conversation stream:

### Proposal Announcement in Switch:
```markdown
📋 **Formal Infrastructure Change Proposal Generated**
- **Proposal ID**: `prop-03b1133ced`
- **Candidate ID**: `cand-01-rightsize-web`
- **Proposal Hash**: `39d1c279a07b49d5...`
- **Status**: `PENDING_APPROVAL`
- **Affected Files**: `docker-compose.yml`
- **Estimated Monthly Savings**: $42.00
- **Security Impact**: NEUTRAL | Reliability Impact: IMPROVED

To approve this change, an authorized lead must run:
`@cloudpilot-ops-agent approve proposal prop-03b1133ced`

To reject this change:
`@cloudpilot-ops-agent reject proposal prop-03b1133ced`
```

### Issuing Approval via Switch:
```
@cloudpilot-ops-agent approve proposal prop-03b1133ced
```
The coordinator inspects the sender's role from event metadata, validates permissions, issues the HMAC token, updates the proposal status to `APPROVED`, and automatically initiates bounded sandbox execution.

