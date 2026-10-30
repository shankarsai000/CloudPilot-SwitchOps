# CloudPilot SwitchOps — Security Audit Rule Catalog

The **SecOps Engine** (`app.services.secops`) evaluates discovered infrastructure configurations against ten deterministic, evidence-based security rules (`SEC-001` through `SEC-010`).

---

## Complete Rule Specification

### SEC-001: Public Redis Exposure
- **Rule ID**: `SEC-001`
- **Target Component**: Docker Compose Redis services
- **Default Severity**: `HIGH`
- **Condition**: Container image contains `redis` and port `6379` is published to host IP `0.0.0.0`, `::`, or wildcard without authentication.
- **Evidence Attached**: Published port mappings, image tag, container service name.
- **Remediation**: Bind listener to `127.0.0.1:6379` or communicate strictly across internal Docker bridge networks without host port exposure.

### SEC-002: Public Database Listener Port
- **Rule ID**: `SEC-002`
- **Target Component**: Docker Compose Database services (Postgres, MySQL, Mongo, MariaDB)
- **Default Severity**: `HIGH`
- **Condition**: Container image or service name matches database engines and publishes ports `5432`, `3306`, `1433`, or `27017` to `0.0.0.0`.
- **Evidence Attached**: Exposed port mapping dictionary, service name, image reference.
- **Remediation**: Remove public host port binding; access database via internal bridge networks or bastion VPN.

### SEC-003: Unrestricted Security Group Ingress (0.0.0.0/0)
- **Rule ID**: `SEC-003`
- **Target Component**: Terraform `aws_security_group`
- **Default Severity**: `CRITICAL` for SSH (22) / RDP (3389); `HIGH` for database listeners
- **Condition**: Ingress rule contains CIDR `0.0.0.0/0` covering port 22, 3389, 5432, 3306, 1433, or 27017.
- **Evidence Attached**: Violating port range, cidr_blocks array, security group name.
- **Remediation**: Restrict ingress to corporate VPN or bastion CIDR blocks; migrate SSH access to AWS Systems Manager Session Manager.

### SEC-004: Privileged Container Execution
- **Rule ID**: `SEC-004`
- **Target Component**: Docker Compose services
- **Default Severity**: `CRITICAL`
- **Condition**: Service configuration specifies `privileged: true`.
- **Evidence Attached**: Privileged flag state, service name.
- **Remediation**: Remove `privileged: true` and specify granular Linux capabilities via `cap_add` only if strictly necessary.

### SEC-005: Host Docker Socket Mount
- **Rule ID**: `SEC-005`
- **Target Component**: Docker Compose volume mounts
- **Default Severity**: `CRITICAL`
- **Condition**: Container volume definitions map `/var/run/docker.sock`.
- **Evidence Attached**: Exact volume mount string, service name.
- **Remediation**: Remove Docker socket mounts; interact with container daemons via authenticated API proxies or separate agent services.

### SEC-006: Host Network Mode Enabled
- **Rule ID**: `SEC-006`
- **Target Component**: Docker Compose services
- **Default Severity**: `HIGH`
- **Condition**: Service specifies `network_mode: "host"`.
- **Evidence Attached**: Network mode string, service name.
- **Remediation**: Switch to user-defined bridge networks and publish only necessary application endpoints.

### SEC-007: S3 Public ACL or Missing Public Access Block
- **Rule ID**: `SEC-007`
- **Target Component**: Terraform `aws_s3_bucket`
- **Default Severity**: `CRITICAL` for public ACL; `MEDIUM` for missing public access block
- **Condition**: Bucket specifies `acl = "public-read"` or workspace lacks an `aws_s3_bucket_public_access_block` resource for the bucket.
- **Evidence Attached**: ACL attribute value, bucket name.
- **Remediation**: Set bucket ACL to `"private"` and configure `aws_s3_bucket_public_access_block` with all four block settings enabled.

### SEC-008: Unencrypted EBS Volume
- **Rule ID**: `SEC-008`
- **Target Component**: Terraform `aws_ebs_volume`
- **Default Severity**: `HIGH`
- **Condition**: Volume declaration sets `encrypted = false` or omits the encryption flag.
- **Evidence Attached**: Encrypted attribute state, volume name.
- **Remediation**: Set `encrypted = true` and specify a KMS key ID.

### SEC-009: Unencrypted RDS Database Instance
- **Rule ID**: `SEC-009`
- **Target Component**: Terraform `aws_db_instance`
- **Default Severity**: `HIGH`
- **Condition**: Database instance declaration sets `storage_encrypted = false` or omits the flag.
- **Evidence Attached**: `storage_encrypted` attribute value, database identifier.
- **Remediation**: Set `storage_encrypted = true` on the RDS instance definition.

### SEC-010: Plain-Text Credentials in Configuration
- **Rule ID**: `SEC-010`
- **Target Component**: Terraform resources and Docker Compose environment blocks
- **Default Severity**: `CRITICAL` for Terraform password attributes; `HIGH` for Compose environment
- **Condition**: Plain-text passwords, tokens, or private keys are statically committed in configuration attributes.
- **Evidence Attached**: Sensitive attribute key name (the secret value itself is always masked or redacted to prevent log leakage).
- **Remediation**: Move static credentials to external secret vaults (e.g. AWS Secrets Manager, SSM Parameter Store, Docker Secrets).
