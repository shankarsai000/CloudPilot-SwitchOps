# CloudPilot SwitchOps — Hackathon Demo Video Script

**Target Duration:** 3–4 Minutes  
**Track:** Flip the Switch — Track 01: Best Business Workflow  
**Presenters:** Lead Cloud Architect / SRE Engineer  

---

## Video Outline & Timestamps

| Timestamp | Segment Title | On-Screen Visual | Audio Narration |
| :---: | :--- | :--- | :--- |
| **00:00 - 00:30** | **The Hook & Problem Statement** | Terminal showing chaotic alert storms & disjointed cloud dashboards. Title slide: *CloudPilot SwitchOps*. | "Welcome to CloudPilot SwitchOps. In modern enterprises, cloud operations are fractured. FinOps uncovers waste in spreadsheets, SecOps raises noisy vulnerability tickets, and SREs fear black-box AI tools that mutate infrastructure without governance. CloudPilot transforms this into a collaborative, human-authorized control room inside Switch AI." |
| **00:30 - 01:15** | **Switch Room Ingestion & Specialist Discovery** | Switch room UI showing human architect prompt: `@cloudpilot-ops-agent decide on staging infrastructure`. Split screen shows AST parser running. | "It starts in the Switch collaboration room. An architect asks CloudPilot to investigate our staging environment. CloudPilot's discovery engine parses Terraform and Docker Compose ASTs, normalizing resources and mapping cross-provider dependencies. Specialist agents immediately analyze cost, security exposure, and reliability in parallel." |
| **01:15 - 01:55** | **Formal Verification: Z3 SMT Solver & Pareto Frontier** | Dashboard Area C: Pareto frontier table and Z3 Theorem Prover badge displaying `Z3_CONSTRAINTS_SAT`. | "Instead of vague heuristics, CloudPilot formulates optimization as a 4-objective problem: balancing cost savings, risk, reliability, and effort. Crucially, we use the Z3 SMT Theorem Prover to formally prove that proposed changes strictly satisfy non-negotiable security invariants: no public database exposure, storage retention, and budget ceiling bounds." |
| **01:55 - 02:40** | **Human-in-the-Loop 14-Point Governance** | Dashboard Area D and Switch room: Formal proposal published with SHA-256 hash and 14-point review checklist. Operator clicks Approve. | "CloudPilot publishes a cryptographically locked change proposal into the Switch room. The proposal locks the exact pre-mutation SHA-256 hash and presents our 14-point review checklist. Notice that an unauthorized viewer cannot approve this. Only an authenticated Platform Lead can grant approval, generating a single-use HMAC-SHA256 authorization token." |
| **02:40 - 03:25** | **Bounded Sandbox Execution & Syntactic Verification** | Terminal and Dashboard Area E: Execution console running in isolated temp sandbox. Terminal outputs verification PASSED. | "Now, the execution phase. Notice our core non-negotiable safety boundary: CloudPilot never touches live cloud APIs or production source files. Changes are cloned to an isolated throwaway sandbox. The engine applies the bounded AST mutation, and an independent parser verifies 100% valid HCL and YAML syntax. If anything drifted, atomic rollback restores the pre-mutation snapshot." |
| **03:25 - 03:50** | **Correlated Audit Trail & Truthful Reporting** | Dashboard Area G showing correlated audit timeline linking Task -> Assessment -> Decision -> Proposal -> Approval -> Execution. | "Finally, the verified outcome is announced back to the Switch room, and our persistent SQLite repository stores an immutable correlation linking the initial task, specialist findings, Z3 proofs, approval token, and execution digest. 243 automated tests pass with 100% coverage." |
| **03:50 - 04:00** | **Conclusion & Call to Action** | GitHub repo link: `github.com/shankarsai000/CloudPilot-SwitchOps`. Hackathon closing slide. | "CloudPilot SwitchOps: Safe, formally verified, human-authorized cloud optimization for Switch AI. Thank you." |

---

## Screen Recording Guidance for Presenters

1. **Terminal Setup:**
   - Use high-contrast dark theme (e.g., Dracula or One Dark Pro).
   - Run `python scripts/demo_submission.py` to demonstrate the automated 18-step golden path.
   - Run `python scripts/demo_submission_negative.py` to demonstrate safety gates (rejection, role escalation rejection, drift detection).
2. **Browser Setup:**
   - Open `http://localhost:8000/dashboard` in full-screen (1080p or 1440p).
   - Demonstrate the Header, Cockpit KPI cards, Area A through G tabs, and interactive approval action.
3. **Pacing:**
   - Keep mouse cursor steady. Hover over the Z3 verification status badge and the pre/post SHA-256 hashes to emphasize cryptographic rigor and formal verification.

