# CloudPilot SwitchOps — Findings & Evidence Data Model

CloudPilot SwitchOps enforces an immutable, verifiable evidence architecture across all specialist findings, inventories, and assessment summaries.

---

## 1. Domain Entities & Schemas

### `Finding` (`app.domain.finding`)
Represents an individual evidence-backed deficiency detected by FinOps, SecOps, or SRE specialist engines.

| Field | Type | Description |
|---|---|---|
| `finding_id` | `str` | Unique finding ID (e.g., `fnd-c8a7b1d2e3`) |
| `task_id` | `str` | Foreign key referencing the parent task |
| `agent_id` | `str` | Specialist identity: `finops-specialist` or `secops-specialist` |
| `category` | `FindingCategory` | `FINOPS`, `SECURITY`, `RELIABILITY`, `DISCOVERY` |
| `rule_id` | `str` | Stable rule code (e.g., `SEC-001`, `FIN-005`, `REL-002`) |
| `severity` | `FindingSeverity` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO` |
| `title` | `str` | Concise issue summary |
| `description` | `str` | Detailed narrative explanation of the risk |
| `source_file` | `str` | Workspace-relative path of the declaring file |
| `source_location` | `Optional[str]` | Line number or resource block identifier |
| `observed_value` | `Any` | Actual detected configuration value |
| `expected_value` | `Any` | Policy baseline or expected value |
| `evidence` | `Dict[str, Any]` | Verifiable proof data and extraction context |
| `recommendation` | `str` | Concrete, actionable remediation instructions |
| `confidence` | `float` | Reproducible confidence score (0.0 to 1.0) |
| `status` | `str` | `OPEN`, `RESOLVED`, `ACCEPTED_RISK` |
| `created_at` | `datetime` | UTC timestamp |
| `schema_version` | `str` | `"1.0"` |

### `AssessmentSummary` (`app.domain.finding`)
Consolidated operational assessment across cost, security, and reliability dimensions for an entire infrastructure workspace.

| Field | Type | Description |
|---|---|---|
| `assessment_id` | `str` | Unique assessment ID (e.g., `asm-f9e8d7c6b5`) |
| `task_id` | `str` | Linked task ID |
| `workspace_root` | `str` | Target scanned directory |
| `total_resources` | `int` | Total count of discovered resources |
| `total_findings` | `int` | Consolidated count of findings |
| `critical_findings_count` | `int` | Count of critical severity findings |
| `high_findings_count` | `int` | Count of high severity findings |
| `medium_findings_count` | `int` | Count of medium severity findings |
| `low_findings_count` | `int` | Count of low severity findings |
| `estimated_monthly_cost` | `str` | Decimal string of total monthly spend in USD |
| `currency` | `str` | Currency code (`"USD"`) |
| `finops_summary` | `str` | FinOps baseline narrative summary |
| `secops_summary` | `str` | SecOps posture summary |
| `reliability_summary` | `str` | SRE resilience posture summary |
| `next_phase_recommendations` | `List[str]` | Actionable items prioritized for Phase 3 optimization |
| `status` | `str` | `COMPLETED`, `PARTIAL`, `FAILED` |
| `created_at` | `datetime` | UTC timestamp |
| `schema_version` | `str` | `"1.0"` |

---

## 2. SQLite Database Schema

The persistence layer (`app.persistence.repository`) maintains dedicated, indexed tables:

```sql
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    category TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_location TEXT,
    observed_value_json TEXT NOT NULL,
    expected_value_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence REAL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inventories (
    inventory_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    workspace_root TEXT NOT NULL,
    resources_json TEXT NOT NULL,
    discovered_files_json TEXT NOT NULL,
    discovery_duration_ms REAL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assessments (
    assessment_id TEXT PRIMARY KEY,
    task_id TEXT UNIQUE NOT NULL,
    workspace_root TEXT NOT NULL,
    total_resources INTEGER NOT NULL,
    total_findings INTEGER NOT NULL,
    critical_findings_count INTEGER NOT NULL,
    high_findings_count INTEGER NOT NULL,
    medium_findings_count INTEGER NOT NULL,
    low_findings_count INTEGER NOT NULL,
    estimated_monthly_cost TEXT NOT NULL,
    currency TEXT NOT NULL,
    finops_summary TEXT,
    secops_summary TEXT,
    reliability_summary TEXT,
    next_phase_recommendations_json TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);
```
