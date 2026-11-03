# CloudPilot SwitchOps — Decision Intelligence REST API Reference

## 1. Overview

The Decision API exposes Phase 3 capabilities via FastAPI endpoints mounted at `/api/v1/decisions`. All endpoints operate strictly in **read-only mode**.

---

## 2. Endpoint Catalog

### `POST /api/v1/decisions/run`
Trigger an autonomous decision intelligence optimization run.
- **Request Body**:
  ```json
  {
    "task_id": "tsk-12345678",
    "workspace_root": "samples/staging",
    "preference_profile": "BALANCED",
    "policy_config": {
      "monthly_budget_ceiling": "200.00",
      "disallow_public_database": true,
      "disallow_privileged_containers": true
    },
    "room_id": "cloudpilot-ops",
    "requested_by": "@lead-architect:switch"
  }
  ```
- **Response**: `DecisionRun` model (HTTP 200).

---

### `GET /api/v1/decisions/{decision_id}`
Retrieve high-level decision run metadata and executive summary.
- **Path Parameter**: `decision_id` (string).
- **Response**: `DecisionRun` model (HTTP 200).

---

### `GET /api/v1/decisions/task/{task_id}`
Retrieve the latest decision run associated with a given assessment task.
- **Path Parameter**: `task_id` (string).
- **Response**: `DecisionRun` model (HTTP 200).

---

### `GET /api/v1/decisions/{decision_id}/candidates`
Retrieve all evaluated candidate changes with objective scores and feasibility status.
- **Query Parameters**:
  - `feasible_only` (bool, default `false`): Filter for feasible candidates only.
  - `pareto_only` (bool, default `false`): Filter for Pareto-optimal candidates only.
- **Response**: `List[CandidateEvaluation]` (HTTP 200).

---

### `GET /api/v1/decisions/{decision_id}/pareto`
Retrieve only the non-dominated Pareto frontier candidates.
- **Response**: `List[CandidateEvaluation]` (HTTP 200).

---

### `GET /api/v1/decisions/{decision_id}/constraints`
Retrieve detailed constraint evaluations, rejection reasons, and Z3 status.
- **Response**:
  ```json
  {
    "decision_id": "dec-a1b2c3d4",
    "z3_verification_status": "Z3_VERIFIED_SAT",
    "total_evaluated": 7,
    "feasible_count": 5,
    "rejected_count": 2,
    "rejected_candidates": [
      {
        "candidate_id": "cand-unsafe-drop-persistence",
        "title": "Drop Persistent Volume to Reduce Cost",
        "rejection_reasons": ["[CONST-REL-01] Stateful persistence violated"],
        "constraint_failures": [...]
      }
    ]
  }
  ```

---

### `GET /api/v1/decisions/{decision_id}/report`
Retrieve the full CTO-grade decision report with complete lineage.
- **Response**: `DecisionReport` model (HTTP 200).
