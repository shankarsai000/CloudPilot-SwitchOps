# CloudPilot SwitchOps — Candidate Generation Engine

## 1. Overview

The Candidate Generation Engine (`CandidateGenerator`) deterministically translates Phase 2 discovered infrastructure inventory and specialist findings into concrete, actionable candidate modifications.

Every candidate change proposal is:
- **Typed**: Classified under standardized `CandidateType` enumerations.
- **Traceable**: Linked directly to `source_finding_ids` and declarative AST definitions.
- **Quantified**: Expressed with exact Decimal financial before/after values and qualitative security/reliability impacts.
- **Reproducible**: Evaluated identically on repeated executions with zero reliance on LLM generation.

---

## 2. Supported Candidate Types

| Candidate Type | Source Finding | Target Resource | Typical Action |
| :--- | :--- | :--- | :--- |
| `RESIZE_COMPUTE` | `FIN-003` | `aws_instance` | Downsize over-provisioned instance (e.g. `t3.xlarge` $\rightarrow$ `t3.medium`) |
| `DOWNGRADE_STORAGE` | `FIN-002` | `aws_ebs_volume` | Terminate or snapshot unattached EBS storage volume |
| `SCHEDULE_DATABASE` | `FIN-001` | `aws_db_instance` | Apply scheduled off-hours shutdown for non-prod databases |
| `RESTRICT_INGRESS` | `SEC-001`, `SEC-004` | `aws_security_group`, `compose.service` | Restrict wildcard `0.0.0.0/0` ingress to authorized bastion/VPN CIDRs |
| `REMOVE_PRIVILEGED` | `SEC-005` | `compose.service` | Drop `privileged: true` flag and switch container to non-root UID |
| `REMOVE_DOCKER_SOCKET` | `SEC-002` | `compose.service` | Remove host `/var/run/docker.sock` mount from container filesystem |
| `ENABLE_ENCRYPTION` | `SEC-003` | `aws_db_instance` | Enable storage encryption at rest with AWS KMS |
| `ADD_HEALTHCHECK` | `REL-002` | `compose.service` | Configure robust HTTP/TCP healthcheck probe with interval/retries |
| `MULTI_AZ_FAILOVER` | `REL-001` | `aws_db_instance` | Enable Multi-AZ deployment for zero-downtime failover |

---

## 3. Adversarial Test Candidates

To prove that the Constraint Engine and Z3 formal solver strictly reject unsafe proposals, the generator produces intentional anti-pattern candidates during test cycles:

1. **`cand-unsafe-drop-persistence`**:
   - Proposed Action: Deletes persistent PostgreSQL Docker volume (`postgres_data`) to reduce disk costs.
   - Intended Rejection: Triggers `CONST-REL-01` (Mandatory persistence for stateful workloads).
2. **`cand-unsafe-expose-db`**:
   - Proposed Action: Binds database port `5432` directly to `0.0.0.0/0` to avoid VPC NAT gateway charges.
   - Intended Rejection: Triggers `CONST-SEC-01` (Disallow public database interfaces).

---

## 4. ProposedChange Schema

Each individual mutation in a candidate proposal follows the strict schema:

```json
{
  "resource_id": "app_staging_ec2",
  "resource_name": "web_server",
  "resource_type": "aws_instance",
  "source_file": "samples/staging/main.tf",
  "attribute_path": "instance_type",
  "current_value": "t3.xlarge",
  "proposed_value": "t3.medium",
  "action_type": "MODIFY"
}
```
