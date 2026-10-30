# CloudPilot SwitchOps — SRE & Reliability Rule Catalog

The **SecOps & SRE Engine** (`app.services.secops`) audits infrastructure resilience and container operational stability against five deterministic reliability rules (`REL-001` through `REL-005`).

---

## Complete Rule Specification

### REL-001: Missing Container Healthcheck
- **Rule ID**: `REL-001`
- **Target Component**: Docker Compose services
- **Default Severity**: `MEDIUM`
- **Condition**: Container service definition does not configure a `healthcheck` block.
- **Risk Impact**: Without liveness/readiness probes, container orchestrators and reverse proxies cannot detect stuck threads, deadlocks, or crashed daemon processes, continuing to direct client traffic to unresponsive containers.
- **Evidence Attached**: Service name, container image.
- **Remediation**: Add a `healthcheck` block defining `test`, `interval`, `timeout`, and `retries`.

### REL-002: Absent or Fragile Restart Policy
- **Rule ID**: `REL-002`
- **Target Component**: Docker Compose services
- **Default Severity**: `LOW`
- **Condition**: Service configuration specifies `restart: "no"`, `restart: "on-failure"`, or omits the restart policy entirely.
- **Risk Impact**: When a host daemon reboots or an unhandled exception causes container termination, the service will not automatically recover without manual operator intervention.
- **Evidence Attached**: Declared restart policy string, service name.
- **Remediation**: Set `restart: unless-stopped` or `restart: always` to guarantee automatic container restoration.

### REL-003: Single Point of Failure (SPOF) Database
- **Rule ID**: `REL-003`
- **Target Component**: Terraform `aws_db_instance`
- **Default Severity**: `MEDIUM`
- **Condition**: Relational database instance declares `multi_az = false` or omits Multi-AZ failover.
- **Risk Impact**: An Availability Zone outage or underlying hardware failure causes immediate application downtime that persists until manual database restoration is performed.
- **Evidence Attached**: `multi_az` boolean flag, database instance identifier.
- **Remediation**: Enable `multi_az = true` or configure an automated read-replica failover pair.

### REL-004: Missing Resource Constraints (Noisy Neighbor Risk)
- **Rule ID**: `REL-004`
- **Target Component**: Docker Compose services
- **Default Severity**: `LOW`
- **Condition**: Service configuration omits `deploy.resources.limits` (CPU and Memory).
- **Risk Impact**: A memory leak or CPU spike in a single co-located container can consume all available host memory, triggering the Linux OOM-killer to terminate critical neighboring processes or the Docker daemon itself.
- **Evidence Attached**: Service name, deployment resources configuration.
- **Remediation**: Specify `deploy.resources.limits` (e.g., `cpus: '1.0'`, `memory: '512M'`).

### REL-005: Stateful Database Missing Persistent Volume
- **Rule ID**: `REL-005`
- **Target Component**: Docker Compose stateful services (Postgres, MySQL, Mongo, Redis, MariaDB)
- **Default Severity**: `HIGH`
- **Condition**: Container runs a stateful database engine image but declares no persistent volume mounts (`volumes`).
- **Risk Impact**: Any container recreation, image upgrade, or host reboot permanently deletes all stored database records and state.
- **Evidence Attached**: Container image, volume mount array, service name.
- **Remediation**: Mount a persistent named Docker volume or host directory to the container data directory (e.g. `/var/lib/postgresql/data`).
