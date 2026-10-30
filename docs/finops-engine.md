# CloudPilot SwitchOps — FinOps Intelligence Engine

The **FinOps Intelligence Engine** (`app.services.finops`) delivers deterministic, evidence-backed cloud infrastructure cost estimation and financial hygiene analysis.

---

## 1. Design Principles & Arithmetic Guarantees

Cloud financial analysis in CloudPilot SwitchOps follows strict engineering standards:

1. **Deterministic Calculation**: Estimates are calculated programmatically from declared infrastructure attributes and versioned rate cards. No arbitrary LLM guessing is used for numbers.
2. **Decimal Monetary Arithmetic**: All monetary quantities, unit rates, multiplier calculations, and sums use Python's `decimal.Decimal` with explicit `ROUND_HALF_UP` quantization to two decimal places (`0.01`). IEEE-754 binary floating point arithmetic is strictly forbidden to prevent precision drift.
3. **Zero Mixed Currencies**: All baseline calculations default to USD (`USD`), explicitly tagged on every item and summary object.
4. **Transparent Provenance**: All rate lookups cite their source catalog version, SKU, and effective baseline hours.

---

## 2. Versioned Pricing Catalog (`data/pricing/catalog-v1.json`)

The engine indexes rate cards from versioned JSON catalogs:

```json
{
  "catalog_version": "1.0",
  "currency": "USD",
  "provenance": {
    "source": "CloudPilot SwitchOps Standard Demonstration Pricing Benchmark",
    "standard_monthly_hours": 730
  },
  "rates": [
    {
      "provider": "aws",
      "region": "us-east-1",
      "sku": "aws_instance:m5.large",
      "resource_type": "compute",
      "pricing_unit": "hour",
      "unit_price": "0.0960",
      "currency": "USD",
      "description": "AWS EC2 m5.large Linux on-demand instance"
    }
  ]
}
```

### Sizing and Pricing Formulations
The standard baseline models `730` operating hours per calendar month:

- **EC2 Compute (`aws_instance`)**:
  $$\text{Monthly Cost} = \text{unit\_price} \times 730\text{ hours}$$
  *(e.g., m5.large @ \$0.0960/hr = \$70.08/month)*
- **EBS Storage (`aws_ebs_volume`)**:
  $$\text{Monthly Cost} = \text{unit\_price} \times \text{size\_gb}$$
  *(e.g., gp3 @ \$0.0800/GB-month; io2 @ \$0.1250/GB-month)*
- **RDS Database (`aws_db_instance`)**:
  $$\text{Monthly Cost} = \text{unit\_price} \times 730\text{ hours}$$
  *(e.g., db.m5.large @ \$0.1360/hr = \$99.28/month)*
- **S3 Bucket Baseline (`aws_s3_bucket`)**:
  $$\text{Monthly Cost} = \text{unit\_price} \times 50\text{ GB (baseline)}$$
- **Application Load Balancer (`aws_lb`)**:
  $$\text{Monthly Cost} = \$0.0225 \times 730\text{ hours} = \$16.425 \approx \$16.43\text{/month}$$
- **Docker Compose Service (`compose_service`)**:
  $$\text{Monthly Cost} = \text{unit\_price} \times 730\text{ hours} \times \text{replicas}$$

---

## 3. Financial Hygiene Rules

The FinOps engine evaluates declarative configurations against five financial hygiene rules:

| Rule ID | Name | Severity | Description | Actionable Remediation |
|---|---|---|---|---|
| **FIN-001** | Potentially Oversized Compute Instance | `MEDIUM` | Instance sizing (`m5.large`, `c5.xlarge`) in non-production tiers incurs unnecessary monthly idle spend. | Downscale to `t3.small` or `t3.medium` for staging and test workloads. |
| **FIN-002** | Unbounded Container Resource Limits | `LOW` | Compose service does not declare `deploy.resources.limits`, risking runaway memory consumption and node over-allocation. | Add explicit `deploy.resources.limits` constraints (e.g. `cpus: '0.5'`, `memory: 512M`). |
| **FIN-003** | Continuous 24/7 Staging Database Runtime | `LOW` | Staging database runs 730 hours/month continuously without off-hours schedule. | Apply scheduled off-hours shutdown (~250-300 hours/mo) or Aurora Serverless pause to capture up to 65% savings. |
| **FIN-004** | Dynamic or Unresolved Pricing Inputs | `LOW` | Resource utilizes dynamic HCL variables for size, instance type, or count without static staging defaults. | Provide explicit staging `.tfvars` or static declarative sizing inputs. |
| **FIN-005** | Costly Provisioned IOPS in Staging | `MEDIUM` | EBS volume configured as `io2` provisioned IOPS SSD in non-production. | Migrate volume from `io2` to `gp3` General Purpose SSD to eliminate IOPS surcharges. |

---

## 4. Itemized Cost Breakdown Contract

The `FinOpsAnalysisResult` contains:
- `task_id`: Linked task identifier
- `workspace_root`: Target scanned workspace
- `total_monthly_cost`: Consolidated monthly baseline in USD (e.g. `"212.83"`)
- `currency`: `"USD"`
- `monthly_hours`: `730`
- `items`: Itemized `ResourceCostBreakdown` records per discovered billable component
- `findings`: Emitted `Finding` records for financial hygiene rule violations
- `summary_text`: Human-readable executive summary narrative
