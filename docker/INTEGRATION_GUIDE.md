# Cost Intelligence Agent (M2-CIA) - Integration Guide

## Integrating M2-CIA with M1-IDA

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     CloudPilot AI Layers                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  M1: Infrastructure Discovery Agent (M1-IDA)               │
│  ├─ AWS, Azure, GCP resource inventory                     │
│  ├─ Resource graph and relationships                       │
│  └─ Resource metadata (name, type, tags, app_id, team_id)  │
│           │                                                 │
│           ▼                                                 │
│  M2: Cost Intelligence Agent (M2-CIA) ← YOU ARE HERE       │
│  ├─ Billing data ingestion (AWS, Azure, GCP)              │
│  ├─ Resource correlation (90%+ accuracy)                   │
│  ├─ Anomaly detection (30% threshold)                      │
│  ├─ Cost forecasting (7/14/30/60/90-day)                  │
│  └─ Team cost aggregation                                  │
│           │                                                 │
│           ▼                                                 │
│  Future: FinOps Recommendations (M3)                       │
│  ├─ Reserved instance optimization                         │
│  ├─ Spot instance recommendations                          │
│  └─ Cost allocation tags validation                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Cloud Billing APIs               M1 Resources Database
        │                               │
        ├─ AWS Cost Explorer            │
        ├─ Azure Cost Management        │
        └─ GCP BigQuery                 │
                │                        │
                ▼                        ▼
        ┌──────────────────────────────────┐
        │   Cost Intelligence Agent (M2)   │
        ├──────────────────────────────────┤
        │                                  │
        │  1. Ingest Billing Data          │
        │  2. Load M1 Resources            │
        │  3. Correlate (90%+ accuracy)    │
        │  4. Detect Anomalies             │
        │  5. Forecast Costs               │
        │  6. Aggregate by Team            │
        │                                  │
        └──────────────────────────────────┘
                │
                ├─ Costs ────────────┐
                ├─ Anomalies ────────┤
                ├─ Forecasts ────────┼─→ PostgreSQL
                ├─ By Team ──────────┤
                └─ Access Logs ──────┘
                        │
                        ▼
                   FastAPI Routes
                   /costs/*
```

## Integration Steps

### 1. **Load M1 Resource Metadata**

M2-CIA requires M1 resource data for correlation. There are two approaches:

#### Option A: Direct Integration (Recommended)
```python
from cost_agent import CostIntelligenceAgent
from infrastructure_discovery_agent import InfrastructureDiscoveryAgent

# Initialize M1 agent
m1_agent = InfrastructureDiscoveryAgent(
    aws_config={"region": "us-east-1"},
    azure_config={"subscription_id": "..."},
    gcp_config={"project_id": "..."}
)

# Get resource graph from M1
resources = m1_agent.discover_all_resources()
# Returns: {"resource-id": {"name": "...", "type": "...", "tags": {...}, "app_id": "...", "team_id": "..."}}

# Initialize M2 agent with M1 resources
m2_agent = CostIntelligenceAgent(
    aws_config={"region": "us-east-1"},
    azure_config={"subscription_id": "..."},
    gcp_config={"project_id": "..."},
    resources=resources  # ← Pass M1 resources here
)
```

#### Option B: Database Integration
```python
# M1 exports resources to PostgreSQL
# M2 reads from shared database
from cost_agent import CostIntelligenceAgent

m2_agent = CostIntelligenceAgent(
    aws_config={"region": "us-east-1"},
    azure_config={"subscription_id": "..."},
    gcp_config={"project_id": "..."}
)

# Load resources from M1 database
from sqlalchemy import create_engine
engine = create_engine("postgresql://localhost/cloudpilot")

# Query M1 resources
m1_resources = {}
with engine.connect() as conn:
    result = conn.execute("""
        SELECT id, name, type, region, tags, app_id, team_id
        FROM resources
        WHERE provider IN ('aws', 'azure', 'gcp')
    """)
    for row in result:
        m1_resources[row['id']] = {
            'name': row['name'],
            'type': row['type'],
            'region': row['region'],
            'tags': row['tags'],
            'app_id': row['app_id'],
            'team_id': row['team_id']
        }

# Pass to M2
m2_agent.update_resources(m1_resources)
```

### 2. **Run Cost Intelligence Pipeline**

```python
import asyncio
from datetime import datetime, timedelta

async def run_cost_pipeline():
    # Calculate date range (last 30 days)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    # Configure cloud accounts
    accounts = {
        'aws': '123456789012',      # AWS account ID
        'azure': 'subscription-id',  # Azure subscription
        'gcp': 'project-id'          # GCP project
    }
    
    # Run complete pipeline
    result = await m2_agent.run_pipeline(
        start_date=start_date,
        end_date=end_date,
        accounts=accounts,
        date=datetime.utcnow().strftime('%Y-%m-%d')
    )
    
    # Result structure:
    # {
    #   'cost_events': [CostEvent, ...],
    #   'anomalies': [CostAnomaly, ...],
    #   'forecasts': [CostForecast, ...],
    #   'by_team': [CostByTeam, ...]
    # }
    
    return result

# Run
result = asyncio.run(run_cost_pipeline())

# Save to PostgreSQL
from cost_repository import CostRepository

repo = CostRepository("postgresql://localhost/costs")
repo.save_cost_events(result['cost_events'])
repo.save_anomalies(result['anomalies'])
repo.save_forecasts(result['forecasts'])
```

### 3. **Set Up Database**

```bash
# Create database
createdb cost_intelligence

# Create tables (M2-CIA will auto-create from schema)
# Tables: cost_events, cost_anomalies, cost_forecasts, cost_access_logs
```

### 4. **Start API Service**

```bash
# Set environment
export DATABASE_URL="postgresql://user:pass@localhost/costs"
export AWS_REGION="us-east-1"
export AWS_PROFILE="default"
export AZURE_SUBSCRIPTION_ID="..."
export GCP_PROJECT_ID="..."

# Start service
python cost_service.py

# Or with Docker
docker build -f Dockerfile.cost -t cost-intelligence:1.0.0 .
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql://user:pass@localhost/costs" \
  -e AWS_REGION="us-east-1" \
  cost-intelligence:1.0.0
```

### 5. **Use Cost Intelligence APIs**

```bash
# Get team costs
curl -H "Authorization: Bearer user-123:manager" \
  http://localhost:8000/api/v1/costs/by-team

# Get anomalies
curl -H "Authorization: Bearer user-123:manager" \
  http://localhost:8000/api/v1/costs/anomalies?severity=critical

# Get forecasts
curl -H "Authorization: Bearer user-123:engineer" \
  http://localhost:8000/api/v1/costs/forecast?days=30

# Trigger ingestion
curl -X POST \
  -H "Authorization: Bearer user-admin:admin" \
  "http://localhost:8000/api/v1/costs/ingest?start_date=2024-01-01&end_date=2024-01-31"
```

## Correlation Strategy with M1

### How M2-CIA Correlates to M1 Resources

**Input from M1:**
```python
{
    "res-001": {
        "name": "web-server-01",
        "type": "instance",
        "provider": "aws",
        "region": "us-east-1",
        "tags": {"env": "prod", "app": "web"},
        "app_id": "app-web",
        "team_id": "team-platform"
    }
}
```

**Input from Billing API:**
```python
BillingLineItem(
    line_item_id="aws-item-123",
    provider="aws",
    resource_id="i-0123456789abcdef0",
    resource_name="web-server-01",
    service="EC2",
    region="us-east-1",
    cost_amount=10.50,
    tags={"env": "prod", "app": "web"}
)
```

**Correlation Process:**
1. **Tag matching:** billing tags {"env": "prod", "app": "web"} match resource tags
   - Confidence: 0.9
   - Match found! ✓

2. **Output:** CostEvent linked to app_id="app-web", team_id="team-platform"
```python
CostEvent(
    cost_event_id="aws-item-123",
    resource_id="res-001",
    resource_name="web-server-01",
    app_id="app-web",
    team_id="team-platform",
    service="EC2",
    daily_cost=10.50,
    correlation_confidence=0.90
)
```

### Correlation Accuracy Improvement

**Best Practices:**
1. **Standardize Tags Across M1**
   - Use consistent tag keys: env, app, owner, cost-center
   - Apply tags at creation time in M1-IDA

2. **Resource Naming Conventions**
   - Follow patterns: `{app}-{component}-{index}`
   - Match billing provider naming
   - M2 uses fuzzy matching as fallback

3. **Keep Resource Metadata Current**
   - Regularly sync M1 resources
   - Update app_id and team_id
   - M2 reloads at each pipeline run

4. **Monitor Correlation Rate**
   - Check: correlation_confidence in cost_events
   - Target: >0.8 average confidence
   - Low confidence → investigate missing tags/metadata

## Team Cost Aggregation

### How M2 Calculates Team Costs

**From M1 Resources:**
- Each resource has team_id
- Each resource has tags (for cost allocation)

**From M2 Cost Events:**
- Each cost event correlates to resource
- Cost event inherits team_id from resource
- Cost event includes app_id from resource

**Aggregation:**
```python
# M2 groups all cost events by team_id
teams = {}
for event in cost_events:
    team_id = event.team_id or "unallocated"
    if team_id not in teams:
        teams[team_id] = {
            'daily': 0,
            'by_service': {},
            'by_category': {}
        }
    
    teams[team_id]['daily'] += event.daily_cost
    teams[team_id]['by_service'][event.service] += event.daily_cost
    teams[team_id]['by_category'][event.cost_category] += event.daily_cost
```

**Example Output:**
```python
CostByTeam(
    team_id="team-platform",
    total_daily_cost=250.50,
    total_monthly_estimate=7515.0,
    cost_by_service={
        "EC2": 150.0,
        "RDS": 80.0,
        "S3": 20.50
    },
    cost_by_category={
        "compute": 150.0,
        "database": 80.0,
        "storage": 20.50
    },
    resource_count=8
)
```

## Anomaly Detection with M1 Context

### Using M1 Metadata for Smarter Anomalies

```python
# Example: EC2 instance upgrade detected via anomaly
anomaly = CostAnomaly(
    anomaly_id="anom-001",
    resource_id="res-001",
    resource_name="web-server-01",
    app_id="app-web",
    team_id="team-platform",
    service="EC2",
    baseline_daily_cost=10.0,
    anomaly_daily_cost=15.0,
    spike_percentage=50.0,
    severity="warning",
    root_cause_hypothesis="Increased instance size or unoptimized workload"
)

# M1 provides context:
# - app_id → notify web team
# - team_id → notify platform team
# - resource_name → specific server
# - tags → environment (prod/staging)
```

## Cost Access Control with M1 Teams

### Authorization Based on M1 Organization

```python
# Setup team membership from M1
from cost_access_control import CostAccessControl

access_control = CostAccessControl()

# Load teams from M1
teams_from_m1 = m1_agent.get_teams()  # {"team-001": {...}, ...}
team_users = m1_agent.get_team_membership()  # {"user-123": ["team-001", "team-002"]}

# Register in M2
for user_id, team_ids in team_users.items():
    access_control.register_user_teams(user_id, team_ids)

# Now M2 enforces M1 org boundaries
# User only sees costs for their M1 teams
allowed = access_control.can_view_cost(
    user_id="user-123",
    user_role="engineer",
    resource_type="team",
    resource_id="team-001",
    team_id="team-001"  # ← From M1
)
# Returns: True if user in team-001
```

## Scheduling Cost Runs

### Daily Cost Intelligence Pipeline

```python
# schedule_cost_runs.py
import asyncio
import logging
from datetime import datetime, timedelta
from cost_agent import CostIntelligenceAgent
from cost_repository import CostRepository

logger = logging.getLogger(__name__)

# Initialize
m2_agent = CostIntelligenceAgent(...)
repo = CostRepository("postgresql://localhost/costs")

async def daily_cost_run():
    """Run cost intelligence pipeline daily."""
    
    # Get previous day
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    
    # Run pipeline for yesterday
    result = await m2_agent.run_pipeline(
        start_date=datetime.combine(yesterday, datetime.min.time()),
        end_date=datetime.combine(today, datetime.min.time()),
        accounts={
            'aws': '123456789012',
            'azure': 'subscription-id',
            'gcp': 'project-id'
        },
        date=str(yesterday)
    )
    
    # Save results
    repo.save_cost_events(result['cost_events'])
    repo.save_anomalies(result['anomalies'])
    repo.save_forecasts(result['forecasts'])
    
    logger.info(f"Daily run complete: {len(result['cost_events'])} events, "
                f"{len(result['anomalies'])} anomalies")

# Schedule with APScheduler
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(
    lambda: asyncio.run(daily_cost_run()),
    'cron',
    hour=1,  # Run at 1 AM
    minute=0
)
scheduler.start()
```

## Monitoring & Alerts

### Key Metrics to Monitor

```python
# In your monitoring system (Datadog, Prometheus, etc.)

# 1. Correlation quality
correlation_rate = sum(1 for event in events if event.correlation_confidence > 0.7) / len(events)
# Target: >90%

# 2. Anomaly detection
anomaly_count = len(anomalies)
# Track: spikes per team, severity distribution

# 3. Forecast accuracy
# Compare predicted costs from previous day to actual
forecast_error = abs(predicted - actual) / actual
# Target: <10% MAPE

# 4. Data freshness
last_ingest_time = repo.get_latest_event_timestamp()
# Target: <24 hours old

# 5. API performance
api_response_time  # Target: <500ms p95
cost_events_latency  # Target: <100ms
anomalies_latency     # Target: <50ms
```

## Troubleshooting

### Low Correlation Rate (<80%)

**Symptoms:** Many cost_events with resource_id=None

**Root Causes:**
1. Missing tags on M1 resources
2. Billing resource names don't match M1
3. Service type mismatch (e.g., "Virtual Machines" vs "VirtualMachine")

**Solutions:**
```python
# Check correlation confidence distribution
from sqlalchemy import create_engine
engine = create_engine("postgresql://localhost/costs")

with engine.connect() as conn:
    result = conn.execute("""
        SELECT 
            correlation_confidence,
            COUNT(*) as count
        FROM cost_events
        GROUP BY correlation_confidence
        ORDER BY correlation_confidence DESC
    """)
    
    for row in result:
        print(f"Confidence {row['correlation_confidence']}: {row['count']} events")

# Add missing tags to M1 resources
# Update service mappings in adapters
# Verify resource naming conventions
```

### High False Positive Rate (>5% of events flagged as anomalies)

**Symptoms:** Many anomalies with spike_percentage just above 30%

**Root Causes:**
1. Baseline calculation insufficient
2. High natural variance (dev environment)
3. Z-score threshold too low

**Solutions:**
```python
# Check historical data length
result = conn.execute("""
    SELECT 
        resource_id,
        COUNT(*) as days_of_history
    FROM cost_events
    GROUP BY resource_id
    HAVING COUNT(*) < 7
""")

# Add more history before anomaly detection
# Exclude dev/test resources (low signal)
# Adjust z-score threshold in anomaly_detector.py
```

### Missing Forecasts

**Symptoms:** Some resources have no forecast

**Root Causes:**
1. Insufficient history (<7 days)
2. New resources not yet ingested
3. Forecast calculation error

**Solutions:**
```python
# Ensure minimum 7-day history
# Check: len(forecaster.history[resource_id]) >= 7

# Use simple forecast as fallback
forecast = forecaster.forecast(event, days=30)
# Returns simple projection if < 7 days history
```

## Production Deployment Checklist

- ✅ M1 resources loaded and validated
- ✅ PostgreSQL database created and migrated
- ✅ Cloud credentials configured (AWS/Azure/GCP)
- ✅ Team membership synced from M1
- ✅ Authorization model configured
- ✅ Daily scheduler setup
- ✅ Monitoring and alerting configured
- ✅ Backup strategy for cost_access_logs
- ✅ Cost data retention policy defined
- ✅ Team notification channels configured

---

**Last Updated:** 2024-01-31  
**Version:** 1.0.0
