# CloudPilot SwitchOps — Infrastructure Discovery Engine

The **Infrastructure Discovery Engine** (`app.services.discovery`) performs autonomous, read-only scanning of target infrastructure workspace directories to identify cloud and container declarations without executing arbitrary code, triggering cloud API mutations, or leaking sensitive credentials.

---

## 1. Design & Security Safeguards

Discovery operates under strict filesystem and execution safeguards:

1. **Explicit Workspace Root**: Discovery is bounded strictly to an operator-designated directory (e.g., `samples/staging` or `samples/safe`). It never recursively scans parent directories or workstation roots.
2. **Directory Traversal Protection**: All paths are resolved and checked using `Path.resolve().relative_to(allowed_base)`. Path traversal attempts (such as `../` or absolute path escapes) raise a typed `ValidationError` and halt processing immediately.
3. **Symlink Escape Checks**: Symlinks targeting locations outside the workspace root are rejected to prevent file extraction or privilege escalation.
4. **File Size Bounds**: Files exceeding `1 MB` (`MAX_FILE_SIZE_BYTES`) are skipped to protect memory and prevent resource exhaustion.
5. **File Count Limits**: Workspaces are restricted to a maximum of 100 configuration files (`MAX_WORKSPACE_FILES`).
6. **Read-Only Invariant**: Discovery parses declarative ASTs directly from disk. It **never** invokes `terraform apply`, `docker compose up`, shell interpreters, or cloud management APIs.
7. **Secret Redaction at Ingestion**: Environment variables containing sensitive keys (`password`, `secret`, `token`, `key`, `auth`) are redacted to `"[REDACTED]"` during parsing and never appear in domain models or logs.

---

## 2. Supported Configuration Formats

### Terraform HCL Parser (`TerraformParser`)
- **Supported Extensions**: `*.tf`, `*.tfvars`
- **Parser Engine**: `python-hcl2` (Lark LALR(1) parser)
- **Extracted Resource Types**:
  - AWS EC2: `aws_instance` (categorized as `COMPUTE`)
  - AWS EBS: `aws_ebs_volume` (categorized as `STORAGE`)
  - AWS RDS: `aws_db_instance`, `aws_rds_cluster_instance` (categorized as `DATABASE`)
  - AWS S3: `aws_s3_bucket`, `aws_s3_bucket_v2`, `aws_s3_bucket_public_access_block` (categorized as `STORAGE` / `SECURITY`)
  - AWS VPC & Firewalls: `aws_security_group` (categorized as `SECURITY`)
  - AWS Load Balancers: `aws_lb`, `aws_alb` (categorized as `NETWORK`)
- **Handling Dynamic Expressions**:
  - Distinguishes **`attributes_known`** (static literal strings, numbers, booleans) from **`attributes_unknown`** (variables like `${var.db_pass}` or `${aws_subnet.main.id}`). Dynamic expressions are never fabricated or guessed.

### Docker Compose Safe YAML Parser (`ComposeParser`)
- **Supported Filenames**: `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, `compose.yaml`
- **Parser Engine**: `PyYAML` using `yaml.safe_load`
- **Extracted Attributes**:
  - Service names and container names
  - Image names and tags
  - Port mappings (host IP, host port, container port, public binding status)
  - Volume mappings (named volumes, bind mounts, socket mounts)
  - Security options (`privileged`, `network_mode`, `cap_add`)
  - Reliability configurations (`restart`, `healthcheck`, `deploy.resources.limits`)
  - Environment variables (with automatic regex redaction of sensitive credentials)

---

## 3. Normalized Domain Representation

Discovered resources are mapped into vendor-neutral domain contracts defined in `app.domain.inventory`:

### `DiscoveredResource`
```python
class DiscoveredResource(BaseModel):
    resource_id: str              # Unique resource identifier (e.g. res-a1b2c3d4)
    resource_type: str            # e.g. aws_instance, compose_service
    provider: str                 # e.g. aws, docker, azure
    name: str                     # Declared name in config
    category: ResourceCategory    # COMPUTE, STORAGE, DATABASE, NETWORK, SECURITY, CONTAINER, OTHER
    source_file: str              # File path relative to workspace
    source_location: str          # Block or line identifier
    configuration: Dict[str, Any] # Full raw parsed configuration
    attributes_known: Dict[str, Any]    # Explicitly known static values
    attributes_unknown: List[str]       # Dynamic or unresolved variables
    discovery_timestamp: datetime # UTC timestamp
    schema_version: str           # "1.0"
```

### `InfrastructureInventory`
Consolidated inventory containing:
- `workspace_root`: Scanned directory path
- `resources`: List of normalized `DiscoveredResource` objects
- `discovered_files`: List of scanned configuration files
- `discovery_duration_ms`: Execution time in milliseconds
- `total_resources`: Calculated resource count
- `created_at`: UTC timestamp

---

## 4. Discovery Execution

Discovery is executed programmatically or through Switch team room commands:

```python
from app.services.discovery.engine import InfrastructureDiscoveryEngine

engine = InfrastructureDiscoveryEngine()
inventory = engine.discover("samples/staging", task_id="task-12345")

print(f"Discovered {inventory.total_resources} resources across {len(inventory.discovered_files)} files in {inventory.discovery_duration_ms:.1f}ms")
```
