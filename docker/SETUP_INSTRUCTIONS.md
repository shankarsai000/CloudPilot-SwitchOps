# CloudPilot AI - Infrastructure Discovery Agent Setup

## Quick Start (5 minutes)

### 1. Move Files to Correct Locations

The agent code is currently in the `docker/` directory. Move files to their proper locations:

```bash
# File relocations (use PowerShell on Windows, bash on Linux/Mac)

# Models
move docker/models_resource.py src/models/resource.py

# Config
move docker/config_credentials.py src/config/credentials.py

# Cloud adapters
move docker/aws_adapter.py src/agents/infrastructure_discovery/cloud_adapters/aws_adapter.py
move docker/azure_adapter.py src/agents/infrastructure_discovery/cloud_adapters/azure_adapter.py
move docker/gcp_adapter.py src/agents/infrastructure_discovery/cloud_adapters/gcp_adapter.py
move docker/kubernetes_adapter.py src/agents/infrastructure_discovery/cloud_adapters/kubernetes_adapter.py

# Agent
move docker/infrastructure_discovery_agent.py src/agents/infrastructure_discovery/agent.py

# Repository
move docker/resource_repository.py src/database/resource_repository.py

# API
move docker/discovery_routes.py src/api/discovery_routes.py

# Tests
move docker/test_infrastructure_discovery.py tests/agents/test_infrastructure_discovery.py

# Documentation
move docker/README_M1_IDA.md README_M1_IDA.md
move docker/Dockerfile.discovery docker/Dockerfile.discovery
```

Or use Python script:

```bash
python docker/__init_files.py
```

### 2. Create Directory Structure

```bash
# Run once to create all __init__.py files
python docker/__init_files.py
```

Directories created:
- `src/models/`
- `src/config/`
- `src/agents/infrastructure_discovery/cloud_adapters/`
- `src/database/`
- `src/api/`
- `tests/agents/`

### 3. Install Dependencies

```bash
# Core dependencies
pip install -r requirements.txt

# Key packages:
pip install boto3                    # AWS SDK
pip install azure-sdk-for-python     # Azure SDK  
pip install google-cloud-python      # GCP SDK
pip install kubernetes               # Kubernetes client
pip install psycopg2-binary          # PostgreSQL driver
pip install pydantic                 # Data validation
pip install fastapi                  # REST framework
pip install uvicorn                  # ASGI server
pip install hvac                     # Vault client (optional)
```

### 4. Set Up Database

```bash
# Create PostgreSQL database
createdb cloudpilot

# Run migrations (creates tables automatically on first connection)
# The agent creates schema on initialization
```

### 5. Configure Credentials

Create `.env` file in project root:

```bash
# AWS
AWS_ACCESS_KEY_ID=your-aws-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_SESSION_TOKEN=your-session-token  # Optional, for temporary credentials

# Azure
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_TENANT_ID=your-tenant-id
AZURE_SUBSCRIPTION_ID=your-subscription-id

# GCP
GCP_PROJECT_ID=your-gcp-project-id
GCP_SERVICE_ACCOUNT_JSON={...}  # Full service account JSON

# Kubernetes
K8S_KUBECONFIG=/path/to/kubeconfig  # Or set KUBECONFIG env var

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/cloudpilot

# Vault (optional, for production)
VAULT_ADDR=https://vault.example.com
VAULT_TOKEN=s.xxxxxxxxxx
VAULT_PATH=secret/cloudpilot

# Logging
LOG_LEVEL=INFO
```

### 6. Run Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
pytest tests/agents/test_infrastructure_discovery.py -v

# Run with coverage
pytest tests/agents/test_infrastructure_discovery.py --cov=src

# Expected output: All tests pass (20+ unit tests, 100% mocked APIs)
```

### 7. Start the Service

**Option A: Direct Python**

```bash
python -m src.agents.infrastructure_discovery.agent
```

Output:
```
INFO - DiscoveryAgent initialized with 4 workers
INFO - Loaded 4 cloud adapters: ['aws', 'azure', 'gcp', 'k8s']
INFO - Starting infrastructure discovery
INFO - aws: discovered 150 resources
INFO - azure: discovered 45 resources
INFO - gcp: discovered 30 resources
INFO - k8s: discovered 200 resources
INFO - Discovery complete: 425 resources, 180 dependencies, 0 failures
```

**Option B: FastAPI Server**

```bash
# Start REST API server
uvicorn src.api.discovery_routes:create_discovery_router --host 0.0.0.0 --port 8000

# Or with FastAPI app factory
cat > main.py << 'EOF'
from fastapi import FastAPI
from src.api.discovery_routes import create_discovery_router

app = FastAPI()
app.include_router(create_discovery_router())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOF

python main.py
```

**Option C: Docker**

```bash
# Build image
docker build -f docker/Dockerfile.discovery -t cloudpilot-discovery:latest .

# Run container
docker run -e AWS_ACCESS_KEY_ID=... \
           -e AWS_SECRET_ACCESS_KEY=... \
           -e AZURE_CLIENT_ID=... \
           -e AZURE_CLIENT_SECRET=... \
           -e AZURE_TENANT_ID=... \
           -e AZURE_SUBSCRIPTION_ID=... \
           -e GCP_PROJECT_ID=... \
           -p 8000:8000 \
           cloudpilot-discovery:latest

# Health check
curl http://localhost:8000/api/discovery/health
```

---

## Verification Checklist

After setup, verify everything is working:

### Code Structure

```bash
# Check all files in place
ls -la src/models/resource.py
ls -la src/config/credentials.py
ls -la src/agents/infrastructure_discovery/agent.py
ls -la src/agents/infrastructure_discovery/cloud_adapters/*.py
ls -la src/database/resource_repository.py
ls -la src/api/discovery_routes.py
ls -la tests/agents/test_infrastructure_discovery.py
```

### Import Validation

```bash
# Verify imports work
python -c "from src.models.resource import CloudResource; print('✓ Models import OK')"
python -c "from src.config.credentials import CredentialManager; print('✓ Credentials import OK')"
python -c "from src.agents.infrastructure_discovery.agent import DiscoveryAgent; print('✓ Agent import OK')"
python -c "from src.agents.infrastructure_discovery.cloud_adapters.aws_adapter import AWSAdapter; print('✓ AWS adapter import OK')"
python -c "from src.database.resource_repository import ResourceRepository; print('✓ Repository import OK')"
python -c "from src.api.discovery_routes import create_discovery_router; print('✓ API routes import OK')"
```

### Type Hints Validation

```bash
# Check with mypy (install: pip install mypy)
mypy src/agents/infrastructure_discovery/agent.py --ignore-missing-imports
mypy src/models/resource.py --ignore-missing-imports
```

Expected: No errors or "Success: all done!"

### Tests

```bash
# Run full test suite
pytest tests/agents/test_infrastructure_discovery.py -v --tb=short

# Expected: All tests pass (20+ unit tests)
# Example passing tests:
#   ✓ TestResourceSchema::test_cloud_resource_creation
#   ✓ TestAWSAdapter::test_aws_discover_ec2_instances
#   ✓ TestDiscoveryAgent::test_deduplication
#   ✓ TestResourceRepository::test_save_and_get_resource
#   ✓ TestEndToEnd::test_discovery_workflow
```

### Database Connection

```bash
# Test PostgreSQL connection
python << 'EOF'
from src.database.resource_repository import ResourceRepository
try:
    repo = ResourceRepository("postgresql://user:password@localhost/cloudpilot")
    stats = repo.get_statistics()
    print(f"✓ Database connected. Stats: {stats}")
except Exception as e:
    print(f"✗ Database error: {e}")
EOF
```

### Credential Loading

```bash
# Test credential manager
python << 'EOF'
from src.config.credentials import CredentialManager
creds = CredentialManager()
aws_key = creds.get("AWS_ACCESS_KEY_ID")
print(f"✓ AWS key loaded: {aws_key[:10] if aws_key else 'NOT SET'}...")
print(f"✓ Credential manager working")
EOF
```

### Discovery Execution

```bash
# Run discovery with mocks (no real cloud calls)
python << 'EOF'
from src.agents.infrastructure_discovery.agent import DiscoveryAgent

agent = DiscoveryAgent()
# This will fail gracefully if no credentials — that's OK
# Just verifies agent initializes
print("✓ DiscoveryAgent initialized successfully")
EOF
```

### API Health Check

```bash
# If running API server
curl http://localhost:8000/api/discovery/health

# Expected response:
# {"status":"healthy","service":"discovery-agent"}
```

---

## File Locations Reference

After moving files, your structure should be:

```
cloudpilot-ai/
├── docker/
│   ├── Dockerfile.discovery        (Docker build file)
│   ├── README_M1_IDA.md           (Architecture docs - also at root)
│   └── [other build files]
│
├── src/
│   ├── models/
│   │   ├── __init__.py
│   │   └── resource.py            (CloudResource, DependencyEdge schemas)
│   ├── config/
│   │   ├── __init__.py
│   │   └── credentials.py         (CredentialManager)
│   ├── agents/
│   │   ├── __init__.py
│   │   └── infrastructure_discovery/
│   │       ├── __init__.py
│   │       ├── agent.py           (DiscoveryAgent orchestrator)
│   │       └── cloud_adapters/
│   │           ├── __init__.py
│   │           ├── aws_adapter.py
│   │           ├── azure_adapter.py
│   │           ├── gcp_adapter.py
│   │           └── kubernetes_adapter.py
│   ├── database/
│   │   ├── __init__.py
│   │   └── resource_repository.py (PostgreSQL repository)
│   └── api/
│       ├── __init__.py
│       └── discovery_routes.py    (FastAPI routes)
│
├── tests/
│   ├── __init__.py
│   └── agents/
│       ├── __init__.py
│       └── test_infrastructure_discovery.py (20+ unit tests)
│
├── README_M1_IDA.md               (Architecture documentation)
├── requirements.txt               (Python dependencies)
├── .env                           (Credentials - do NOT commit)
└── .gitignore                     (Exclude .env, __pycache__, etc.)
```

---

## Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'src'"

**Solution**: Ensure `src/__init__.py` exists:
```bash
touch src/__init__.py
touch src/models/__init__.py
touch src/config/__init__.py
touch src/agents/__init__.py
touch src/agents/infrastructure_discovery/__init__.py
touch src/agents/infrastructure_discovery/cloud_adapters/__init__.py
touch src/database/__init__.py
touch src/api/__init__.py
```

### Issue: "psycopg2 not installed"

**Solution**: Install PostgreSQL driver:
```bash
pip install psycopg2-binary
```

### Issue: "No module named 'boto3'"

**Solution**: Install AWS SDK:
```bash
pip install boto3
```

### Issue: Tests fail with "ModuleNotFoundError"

**Solution**: Run tests from project root:
```bash
cd /path/to/cloudpilot-ai
pytest tests/agents/test_infrastructure_discovery.py
```

### Issue: "No credentials available, skipping AWS adapter"

**Solution**: This is normal if AWS credentials not set. Set them:
```bash
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
```

### Issue: Discovery finds 0 resources

**Solution**: Check logs:
```bash
python -m src.agents.infrastructure_discovery.agent 2>&1 | head -20
```

Look for credential errors or network issues.

---

## Next Steps

1. ✅ **Files relocated** → All 12 files in correct locations
2. ✅ **Dependencies installed** → pip install requirements
3. ✅ **Tests passing** → pytest tests/agents/
4. ✅ **Discovery working** → agent.discover() returns resources
5. ⏭️ **Save to database** → repo.save_resources(graph.resources)
6. ⏭️ **Integrate with M2** → Cost Intelligence agent queries M1 API
7. ⏭️ **Deploy to production** → docker build + docker run

---

## Requirements.txt

Create `requirements.txt`:

```
# Core discovery
boto3>=1.26.0
azure-sdk-for-python>=1.14.0
google-cloud>=0.34.0
kubernetes>=27.0.0
psycopg2-binary>=2.9.0

# Data models
pydantic>=2.0.0

# API framework
fastapi>=0.95.0
uvicorn>=0.20.0

# Credentials
hvac>=1.0.0

# Testing
pytest>=7.0.0
pytest-cov>=4.0.0

# Logging & utilities
python-dotenv>=0.20.0
```

Save as `requirements.txt`, then:

```bash
pip install -r requirements.txt
```

---

## Support

Refer to `README_M1_IDA.md` for:
- Architecture details
- Design decisions
- Usage examples
- API documentation
- Troubleshooting guide
- Performance benchmarks

For questions, contact the CloudPilot AI infrastructure team.
