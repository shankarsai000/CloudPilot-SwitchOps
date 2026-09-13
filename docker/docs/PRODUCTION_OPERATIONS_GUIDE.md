# CloudPilot AI: Production Operations & Hardening Guide

---

## Overview

This guide establishes standard operating procedures (SOPs), deployment configurations, resilience policies, and disaster recovery runbooks for operating **CloudPilot AI** in enterprise production environments across AWS, Google Cloud, Microsoft Azure, and Kubernetes.

---

## Table of Contents

1. [Deployment Architecture & Containerization](#1-deployment-architecture--containerization)
2. [Secrets Management & Credential Rotation](#2-secrets-management--credential-rotation)
3. [Monitoring, Metrics & Observability](#3-monitoring-metrics--observability)
4. [Incident Response & Emergency Stop (Kill Switch)](#4-incident-response--emergency-stop-kill-switch)
5. [Rollback Procedures & Idempotency](#5-rollback-procedures--idempotency)
6. [Backups, Checkpoints & Retention](#6-backups-checkpoints--retention)
7. [Disaster Recovery & Business Continuity](#7-disaster-recovery--business-continuity)
8. [High Availability & Autoscaling](#8-high-availability--autoscaling)

---

## 1. Deployment Architecture & Containerization

### Architecture Topology
CloudPilot AI operates as a resilient, stateless control plane backed by PostgreSQL (state store) and Redis (locks, task queue, and event pub/sub):

```
                       [ Load Balancer / Ingress (TLS 1.3) ]
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
   [ CloudPilot Pod 1 ]      [ CloudPilot Pod 2 ]      [ CloudPilot Pod N ]
   (FastAPI + Command Center) (FastAPI + Command Center) (FastAPI + Command Center)
            │                         │                         │
            ├─────────────────────────┴─────────────────────────┤
            ▼                                                   ▼
   [ PostgreSQL Cluster ]                              [ Redis Sentinel/Cluster ]
   (Read/Write Primary + Replicas)                     (Distributed Locks & Streams)
```

### Production Dockerfile (`Dockerfile`)
```dockerfile
# Multi-stage production container
FROM python:3.14-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Install minimal OS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy platform source
COPY docker/ /app/docker/

# Create non-root system user
RUN useradd -u 10001 -m -s /bin/bash cloudpilot && \
    chown -R cloudpilot:cloudpilot /app
USER cloudpilot

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD curl -f http://127.0.0.1:8000/api/v1/health/liveness || exit 1

CMD ["uvicorn", "main:app", "--app-dir", "docker", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Kubernetes Deployment Spec
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cloudpilot-control-plane
  namespace: cloudpilot-system
  labels:
    app.kubernetes.io/name: cloudpilot
spec:
  replicas: 3
  selector:
    matchLabels:
      app.kubernetes.io/name: cloudpilot
  template:
    metadata:
      labels:
        app.kubernetes.io/name: cloudpilot
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        fsGroup: 10001
      containers:
        - name: control-plane
          image: cloudpilot/platform:v1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: cloudpilot-config
            - secretRef:
                name: cloudpilot-secrets
          resources:
            requests:
              cpu: "1000m"
              memory: "2Gi"
            limits:
              cpu: "4000m"
              memory: "8Gi"
          livenessProbe:
            httpGet:
              path: /api/v1/health/liveness
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /api/v1/health/readiness
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
```

---

## 2. Secrets Management & Credential Rotation

### Principles
1. **Zero Secret Leakage**: All sensitive values are wrapped in `SecretString`. Output formatting (`__str__`, `__repr__`) returns `***MASKED_SECRET***`.
2. **Short-Lived Temporary Credentials**:
   - **AWS**: STS AssumeRole with 1-hour session tokens.
   - **GCP**: Workload Identity / OAuth2 bearer tokens with 1-hour TTL.
   - **Azure**: Managed Identity (MSI) / Service Principal tokens.
   - **Kubernetes**: Projected ServiceAccount tokens.
3. **Least Privilege**:
   - Role policies are validated against `LeastPrivilegeValidator`.
   - Wildcards (`*`, `*:*`) and destructive write actions are strictly forbidden on read-only providers.
   - **AWS Adapter Safety Constraint**: Defaults to `READ_ONLY` mode. Any mutating call raises `ReadOnlyViolationError`.

### Zero-Downtime Credential Rotation Runbook
Trigger rotation via secure API:
```bash
curl -X POST https://cloudpilot.internal/api/v1/providers/aws/credentials/rotate \
  -H "Authorization: Bearer ${SECOPS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "operator": "secops-engineer",
    "new_credentials": {
      "auth_type": "STS_ASSUME_ROLE",
      "region": "us-east-1",
      "role_arn": "arn:aws:iam::123456789012:role/CloudPilotRotatedRole",
      "access_key": "AKIA...",
      "secret_key": "..."
    }
  }'
```
- **Pre-rotation validation**: CloudPilot verifies new credentials before swapping out active ones.
- **Audit Logging**: A SHA-256 fingerprint of the rotation event is registered without exposing raw keys.

---

## 3. Monitoring, Metrics & Observability

### Prometheus Metrics Endpoints
Accessible at `GET /api/v1/providers/resilience/metrics`:
- `cloudpilot_provider_rate_limit_available_tokens{provider="aws"}`: Remaining token bucket capacity.
- `cloudpilot_provider_rate_limit_throttled_total{provider="gcp"}`: Count of 429 throttles.
- `cloudpilot_circuit_breaker_state{provider="azure"}`: State enum (`0=CLOSED`, `1=HALF_OPEN`, `2=OPEN`).
- `cloudpilot_circuit_breaker_trips_total{provider="aws"}`: Total circuit breaker trip count.
- `cloudpilot_operation_latency_seconds_bucket`: Latency histogram across cloud discovery and mutations.

### Alerting Thresholds
| Alert | Condition | Severity | Action |
| :--- | :--- | :--- | :--- |
| **CircuitBreakerOpen** | `circuit_breaker_state == 2` for > 30s | **P1 (Critical)** | Page on-call SRE; verify cloud provider regional status page. |
| **RateLimitExhaustion** | `rate_limit_available_tokens < 2` for > 1m | **P2 (High)** | Inspect agent call frequency; increase token bucket capacity. |
| **AuthFailureSpike** | `auth_errors_total > 5` in 5m | **P1 (Critical)** | Trigger credential rotation; inspect STS / OAuth token refreshers. |
| **EmergencyStopEngaged** | `emergency_stop_active == 1` | **P1 (Info/Alert)** | Notify engineering leads and incident response team. |

---

## 4. Incident Response & Emergency Stop (Kill Switch)

### Emergency Stop (Global Kill Switch)
If abnormal cloud operations or security anomalies occur, immediately engage the authoritative Emergency Stop:

#### Engaging Emergency Stop
```bash
curl -X POST https://cloudpilot.internal/api/v1/governance/emergency/engage \
  -H "Authorization: Bearer ${OPERATOR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "global",
    "reason": "Security anomaly detected; freezing all autonomous mutating operations",
    "activated_by": "on-call-sre"
  }'
```
- **Effect**: All provider mutations, agent sandbox executions, and GitOps Apply operations are authoritatively rejected (`EMERGENCY_STOP_ACTIVE`). Read-only discovery and monitoring continue safely.

#### Releasing Emergency Stop
```bash
curl -X POST https://cloudpilot.internal/api/v1/governance/emergency/release \
  -H "Authorization: Bearer ${OPERATOR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "global",
    "reason": "Post-incident investigation complete; safety confirmed",
    "operator": "on-call-sre"
  }'
```

---

## 5. Rollback Procedures & Idempotency

### Deterministic Rollback Guarantee
Every mutating operational action is executed through the GitOps / Terraform engine or Phase 6 Rollback Engine:
1. **State Snapshot**: Pre-action infrastructure configuration is snapshotted before execution.
2. **Inverse Operation Formulation**: The exact deterministic inverse action is generated (e.g., `SCALE_UP` for `SCALE_DOWN`, state rollback for Terraform).
3. **Idempotency**: Rollback calls can be executed multiple times without side effects or cascading drift.
4. **Outcome SLA Verification**: Post-rollback telemetry verifies latency and availability return to baseline.

### Triggering Manual or Automated Rollback
```bash
curl -X POST https://cloudpilot.internal/api/v1/providers/gitops/pipeline \
  -H "Authorization: Bearer ${OPERATOR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "stage": "rollback",
    "plan_id": "tf-plan-12345",
    "operator": "on-call-sre"
  }'
```

---

## 6. Backups, Checkpoints & Retention

1. **PostgreSQL Database**:
   - Continuous WAL archiving to S3/GCS bucket with point-in-time recovery (PITR) up to 35 days.
   - Daily automated logical backups with SHA-256 integrity verification.
2. **Redis State**:
   - AOF (Append-Only File) enabled with `everysec` fsync policy.
   - RDB snapshots taken every 15 minutes.
3. **Audit Trails**:
   - All Phase 5 & Phase 8 cryptographic audit logs are replicated to write-once-read-many (WORM) compliant storage with a 7-year retention policy.

---

## 7. Disaster Recovery & Business Continuity

| Metric | Target | Verified in Test Suite |
| :--- | :--- | :--- |
| **Recovery Point Objective (RPO)** | $< 1\text{ minute}$ | Validated via WAL stream replication and transaction logging |
| **Recovery Time Objective (RTO)** | $< 5\text{ minutes}$ | Validated via multi-pod warm standby and automated health failover |

### Regional Failover Runbook
1. Update DNS / Global Load Balancer to route traffic to secondary region.
2. Promote secondary PostgreSQL cluster to read-write primary (`pg_ctl promote`).
3. Point CloudPilot pods in secondary region to promoted database.
4. Verify provider health checks: `GET /api/v1/providers`.

---

## 8. High Availability & Autoscaling

### Horizontal Pod Autoscaler (HPA)
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: cloudpilot-hpa
  namespace: cloudpilot-system
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: cloudpilot-control-plane
  minReplicas: 3
  maxReplicas: 12
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

### Rate Limiting & Concurrency Controls
- **Token Bucket Rate Limiter**: Configured per provider/region to prevent upstream cloud 429 throttling.
- **Action Lock Manager**: Distributed mutual exclusion locks with 300s TTL prevent race conditions on target cloud resources.
- **Circuit Breaker**: Trips to `OPEN` after 3 consecutive failures; self-heals after 5 seconds via `HALF_OPEN` probing.
