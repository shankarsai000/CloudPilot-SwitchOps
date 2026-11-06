# CloudPilot SwitchOps — Submission Screenshots & Visual Artifacts

**Release Tag:** `v4.3.0-submission-ready`  
**Track:** Flip the Switch — Track 01: Best Business Workflow  

---

## Screenshot Inventory & Visual Artifact Checklist

| Screenshot ID | Title | Key Elements Shown | Capturing Instructions |
| :--- | :--- | :--- | :--- |
| **SCR-01** | **Master Cockpit Overview** | KPI cards (9 Resources, $232.29 Baseline Spend, $54.90 Savings, Z3 SAT status), Active Workflow State, Switch Collaboration Telemetry. | Navigate to `http://localhost:8000/dashboard#overview` after clicking "Run Assessment & Decision". |
| **SCR-02** | **Area A: Infrastructure Explorer** | Normalized inventory table showing Terraform (`aws_instance`, `aws_db_instance`, `aws_s3_bucket`) and Docker Compose (`redis`, `postgres`, `admin_daemon`) resources. | Click sidebar: "Area A: Infrastructure". |
| **SCR-03** | **Area B: Specialist Multi-Agent Intelligence** | Three cards side-by-side: FinOps Intelligence (baseline spend, identified waste, offline catalog disclaimer), SecOps Posture (severity breakdown), SRE Reliability (SPOF checks). | Click sidebar: "Area B: Specialists". |
| **SCR-04** | **Area C: Decision Intelligence & Z3 Solver** | Z3 Theorem Prover formal solver badge (`Z3_CONSTRAINTS_SAT`), 4-objective Pareto optimal frontier table, recommended candidate action. | Click sidebar: "Area C: Decisions & Z3". |
| **SCR-05** | **Area D: Human Approval Center** | Active change proposal details, locked SHA-256 pre-mutation hash, 14-point review checklist, HCL diff preview, and Approve/Reject action buttons. | Click sidebar: "Area D: Approval Center". |
| **SCR-06** | **Area E: Bounded Sandbox Execution** | Isolated sandbox workspace path (`tempfile` directory), pre-mutation hash, post-mutation hash, syntactic verification status (PASSED), and live terminal console. | Click sidebar: "Area E: Sandbox Execution" after clicking Execute. |
| **SCR-07** | **Area F: Switch Collaboration Wire Telemetry** | Switch room telemetry, bridge endpoint (`http://localhost:8080`), truthful connection mode badge (`EMULATED`), and published in-room event feed. | Click sidebar: "Area F: Switch Collab". |
| **SCR-08** | **Area G: Correlated Audit Trail** | End-to-end lineage visualization correlating Task ID -> Decision ID -> Proposal ID -> Approval Token -> Execution ID with timestamps. | Click sidebar: "Area G: Correlated Audit". |
| **SCR-09** | **CLI Golden Path Demonstration** | Full 18-step terminal execution of `python scripts/demo_submission.py` showing all green checkmarks and correlated audit summary. | Run `python scripts/demo_submission.py` in 80x24 terminal. |
| **SCR-10** | **CLI Safety Gates Demonstration** | 5 safety gates of `python scripts/demo_submission_negative.py` showing human rejection halt, untrusted caller rejection, hash mismatch abort, and replay prevention. | Run `python scripts/demo_submission_negative.py`. |
| **SCR-11** | **Automated Test Suite Execution** | Pytest summary showing 243 passed in under 40 seconds with 100% pass rate. | Run `pytest tests docker/tests/test_platform_foundation.py -q`. |

---

## Visual Design System & Aesthetics

All dashboard views adhere to the **Command Center Design System**:
- **Palette:** Calm, professional enterprise-grade dark theme (`#0a0e17` background, `#111827` elevated surface, `#1e293b` borders).
- **Accents:** Formal mathematical proofs highlighted in Cyan (`#06b6d4`), verified security status in Emerald (`#10b981`), critical findings in Amber/Crimson (`#f59e0b` / `#ef4444`).
- **Typography:** Inter for high legibility data tables, Outfit for clear hierarchy headers, and ui-monospace for cryptographic SHA-256 hashes and HCL diffs.
- **Zero Mock Buttons:** Every button on every screen triggers live backend REST API calls.
