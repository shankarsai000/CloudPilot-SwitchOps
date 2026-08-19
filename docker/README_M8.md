# M8 — Learning Agent (LEA)

## Module ID
**M8-LEA**

## Layer
Organizational Intelligence & Continuous Learning Layer

## Overview
The Learning Agent gives CloudPilot long-term organizational memory. Instead of making decisions from static rules, CloudPilot improves after every deployment, rollback, optimization, approval, incident, and failure.

## Architecture
Event-driven learning system where every infrastructure event becomes a permanent learning signal.

```
Infrastructure Event
        │
        ▼
  Event Store (Organizational Memory)
        │
        ▼
  Learning Pipeline
        │
        ├── Cloud DNA Builder
        ├── Pattern Detector
        ├── Knowledge Graph Updater
        ├── Experience Replay
        └── Recommendation Optimizer
        │
        ▼
  Updated Organizational Intelligence
```

## Components

| File | Purpose |
|------|---------|
| `models_learning.py` | Domain models (events, DNA, experience, feedback, patterns, graph entities, metrics) |
| `organizational_memory.py` | Append-only event store |
| `cloud_dna_builder.py` | Builds evolving organizational Cloud DNA profiles |
| `knowledge_graph.py` | In-memory directed graph with BFS, subgraph extraction |
| `pattern_detector.py` | Identifies recurring operational patterns |
| `feedback_engine.py` | Collects human feedback on recommendations |
| `experience_replay.py` | Similarity-based historical outcome replay |
| `recommendation_optimizer.py` | Bayesian confidence evolution |
| `policy_learner.py` | Discovers organizational best practices |
| `metrics_evaluator.py` | Calculates continuous improvement KPIs |
| `learning_engine.py` | Core learning pipeline orchestrator |
| `learning_agent.py` | Main agent orchestrator |
| `learning_repository.py` | PostgreSQL persistence for events, DNA, feedback |
| `knowledge_repository.py` | PostgreSQL persistence for knowledge graph |
| `learning_routes.py` | FastAPI router (9 endpoints) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/learning/health` | Health check |
| GET | `/api/learning/profile` | Agent profile summary |
| GET | `/api/learning/cloud-dna` | Cloud DNA profile |
| GET | `/api/learning/patterns` | Detected patterns |
| GET | `/api/learning/history` | Event history |
| GET | `/api/learning/experience` | Experience replay queries |
| GET | `/api/learning/recommendations` | Optimized recommendation scores |
| POST | `/api/learning/feedback` | Submit human feedback |
| POST | `/api/learning/retrain` | Trigger re-evaluation |

## Cloud DNA Model

| Attribute | Example |
|-----------|---------|
| Deployment Style | Conservative |
| Risk Tolerance | Low |
| Scaling Pattern | Predictive |
| Peak Hours | 09:00-17:00 |
| Rollback Frequency | 1.2% |
| Automation Level | 78% |

## Dependencies
- M1 Infrastructure Discovery
- M2 Cost Intelligence
- M3 Application Intelligence
- M4 Risk Intelligence
- M5 Strategy Agent
- M6 Digital Twin Simulation
- M7 Explainability Engine

## Design Patterns
- Event Sourcing
- CQRS (read/write separation)
- Observer Pattern
- Repository Pattern
- Knowledge Graph Pattern
- Strategy Pattern
- Dependency Injection
