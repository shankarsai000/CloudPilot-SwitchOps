# M9 — Decision Engine (DE)

## Module ID
**M9-DE**

## Layer
Executive Decision Intelligence Layer

## Overview
The Decision Engine is the final reasoning engine in CloudPilot. It acts as a **Decision Council** where all intelligence modules (M1–M8) vote independently. The Decision Engine integrates consensus voting, policy validation, conflict resolution, weighted scoring, and confidence calculations to determine the final state of an infrastructure change recommendation.

## Architecture

```
                  Decision Council
                         │
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│          │          │          │          │          │
Discovery Cost       Risk     Strategy   Learning   Simulation
    │      │          │          │          │          │
    └──────┴──────────┼──────────┼──────────┴──────────┘
                      │
              Consensus Manager
                      │
              Conflict Resolver
                      │
              Policy Validator
                      │
           Confidence Calculator
                      │
               Scoring Engine
                      │
               Approval Router
                      │
                Final Decision (APPROVED/REJECTED/etc.)
                      │
          Execution Package Builder
                      │
                 M10 Execution
```

## Decision Council voting process:
1. Each module votes independently (APPROVE, REJECT, ABSTAIN, CONDITIONAL).
2. **Consensus Manager** determines if there is unanimous or majority agreement.
3. **Conflict Resolver** arbitrates any conflicting votes (e.g. Risk rejecting while Strategy approves).
4. **Policy Validator** runs checks against business hours, maintenance windows, security requirements, regional limits, and active change freezes.
5. **Confidence Calculator** aggregates individual module confidences.
6. **Scoring Engine** evaluates a composite score (0-100) using configurable weights.
7. **Approval Router** matches the risk category and savings against thresholds to route approval levels.
8. **Execution Package Builder** outputs a serialized package containing the rollback plan and step list for M10.

## Component Map

| File | Purpose |
|------|---------|
| `models_decision.py` | Unified Pydantic models for decisions, overrides, execution packages |
| `consensus_manager.py` | Voting consensus aggregator |
| `scoring_engine_decision.py` | Configurable weighted decision score calculator |
| `conflict_resolver.py` | Vote conflict arbitration engine |
| `approval_router.py` | Routes approvals (Auto Execute, Lead, SRE, Security, Executive) |
| `policy_validator.py` | Enforces compliance, business hours, and change freezes |
| `confidence_calculator_decision.py` | Aggregates voting confidence levels |
| `execution_package_builder.py` | Assembles M10 automation package with rollback steps |
| `audit_logger.py` | Immutable decision audit log recorder |
| `override_manager.py` | Human override applicator |
| `decision_engine_core.py` | Decision Council pipeline runner |
| `decision_agent.py` | Main orchestrator agent |
| `decision_repository.py` | PostgreSQL persistence |
| `decision_routes.py` | FastAPI router (8 endpoints) |

## Configurable Scoring Formula
The Decision Score is computed as a weighted sum of:
- Business Value (default 25%)
- Risk (default 25%)
- Simulation (default 15%)
- Learning (default 15%)
- ROI (default 10%)
- Policies (default 5%)
- Confidence (default 5%)

All weights are fully customizable at initialization.
