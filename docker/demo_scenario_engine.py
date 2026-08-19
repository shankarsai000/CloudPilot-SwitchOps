"""
CloudPilot Demo Environment - Scenario Engine (v2)

Generates enterprise environments for 10 distinct profiles:
- Startup
- Healthcare
- Manufacturing
- Gaming
- AI Startup
- SaaS
- Financial Services
- Government
- Media
- Retail
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ScenarioEngine:
    """Generates consistent enterprise profiles for CloudPilot AI simulations."""

    def __init__(self, seed: Optional[int] = 42) -> None:
        """Initialize Scenario Engine."""
        self.seed = seed
        self.active_profile: str = "Startup"
        self.resources: list[dict[str, Any]] = []
        self.costs: list[dict[str, Any]] = []
        self.applications: list[dict[str, Any]] = []
        self.opportunities: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.pipeline_progress: dict[str, str] = {
            "M1_IDA": "PENDING",
            "M2_CIA": "PENDING",
            "M3_AIA": "PENDING",
            "M4_RIA": "PENDING",
            "M5_SA": "PENDING",
            "M6_DTS": "PENDING",
            "M7_EE": "PENDING",
            "M8_LEA": "PENDING",
            "M9_DE": "PENDING",
            "M10_AEA": "PENDING",
        }

    def generate_scenario(self, profile: str = "Startup") -> dict[str, Any]:
        """Generate full dataset for the selected enterprise profile."""
        self.active_profile = profile
        if self.seed is not None:
            random.seed(self.seed)

        logger.info("Generating scenario for profile: %s", profile)

        self.resources.clear()
        self.costs.clear()
        self.applications.clear()
        self.opportunities.clear()
        self.events.clear()

        # Route to scenario generator helper
        if profile == "Healthcare":
            self._generate_healthcare_profile()
        elif profile == "Manufacturing":
            self._generate_manufacturing_profile()
        elif profile == "Gaming":
            self._generate_gaming_profile()
        elif profile == "AI Startup" or profile == "AI":
            self._generate_ai_profile()
        elif profile == "SaaS":
            self._generate_saas_profile()
        elif profile == "Financial Services" or profile == "Banking":
            self._generate_financial_profile()
        elif profile == "Government":
            self._generate_government_profile()
        elif profile == "Media":
            self._generate_media_profile()
        elif profile == "Retail" or profile == "E-commerce":
            self._generate_retail_profile()
        else:
            self._generate_startup_profile()

        return {
            "profile": self.active_profile,
            "resource_count": len(self.resources),
            "application_count": len(self.applications),
            "monthly_cost_usd": sum(c.get("cost_monthly", 0.0) for c in self.resources),
            "opportunities_count": len(self.opportunities),
        }

    def get_live_telemetry(self, target_id: str) -> dict[str, Any]:
        """Produce live metrics every few seconds for UI display."""
        if self.seed is not None:
            random.seed(datetime.now().second + hash(target_id))

        return {
            "target_id": target_id,
            "timestamp": datetime.utcnow().isoformat(),
            "cpu_percent": round(random.uniform(15.0, 85.0), 2),
            "memory_percent": round(random.uniform(30.0, 75.0), 2),
            "network_in_mbps": round(random.uniform(5.0, 150.0), 2),
            "network_out_mbps": round(random.uniform(10.0, 300.0), 2),
            "error_rate": round(random.uniform(0.0, 0.01), 4),
            "latency_ms": round(random.uniform(20.0, 180.0), 2),
            "availability": 1.0 if random.random() > 0.001 else 0.0,
        }

    def get_copilot_response(self, query: str) -> str:
        """Answers chatbot queries based on active scenario state."""
        q = query.lower()
        profile = self.active_profile

        if "bill" in q or "cost" in q or "spend" in q:
            monthly_cost = sum(c.get("cost_monthly", 0.0) for c in self.resources)
            wasted = sum(o.get("savings_monthly", 0.0) for o in self.opportunities)
            return (
                f"Your active environment ({profile}) has a monthly cost of **${monthly_cost:,.2f}**. "
                f"CloudPilot detected **${wasted:,.2f}** monthly wasted spend. "
                "The main cost drivers are compute resources and idle database instances."
            )

        if "gpu" in q:
            if profile in ("AI Startup", "AI"):
                return (
                    "Yes, I detected 2 idle GPU training nodes (`ml-gpu-training-3`, `ml-gpu-training-4`) "
                    "with CPU utilization under 5% outside business hours. Scaling them down during off-hours "
                    "will save **$9,000/month**."
                )
            return "There are no GPU training clusters present in this enterprise profile."

        if "risky" in q or "risk" in q:
            opp_risks = [o for o in self.opportunities if o.get("risk") in ("HIGH", "CRITICAL")]
            if opp_risks:
                return (
                    f"Found {len(opp_risks)} high-risk optimization opportunities in this scenario. "
                    f"Specifically, resizing database `{opp_risks[0]['target_id']}` requires executive sign-off "
                    "to prevent read/write bottlenecks."
                )
            return "No critical/high risk optimization items were found in the current scenario."

        if "save" in q or "optimization" in q or "opportunity" in q:
            wasted = sum(o.get("savings_monthly", 0.0) for o in self.opportunities)
            return (
                f"For the **{profile}** profile, CloudPilot identifies **${wasted:,.2f}** in monthly optimizations. "
                "Top recommendations include right-sizing oversized database units and removing idle microservices."
            )

        return (
            f"As your CloudPilot Copilot, I've analyzed the **{profile}** workspace. "
            "I have access to the Infrastructure Graph (M1), Cost baseline (M2), Application dependencies (M3), "
            "and active optimization strategies (M5). You can ask me to find wasted compute or show risky components."
        )

    # ═══════════════════════════════════════════════════════════════
    # Scenario Profile Generators
    # ═══════════════════════════════════════════════════════════════

    def _generate_startup_profile(self) -> None:
        self.applications = [
            {"id": "app-auth", "name": "Authentication", "owner": "Alice", "team": "SecOps", "criticality": "HIGH"},
            {"id": "app-web", "name": "Web Frontend", "owner": "Bob", "team": "Frontend", "criticality": "MEDIUM"},
            {"id": "app-db", "name": "User Database", "owner": "Charlie", "team": "Database", "criticality": "HIGH"},
        ]
        self.resources = [
            {"id": "ec2-auth-1", "name": "auth-server", "type": "EC2", "provider": "AWS", "cost_monthly": 150.0, "state": "RUNNING"},
            {"id": "ec2-web-1", "name": "web-server", "type": "EC2", "provider": "AWS", "cost_monthly": 80.0, "state": "RUNNING"},
            {"id": "rds-db-1", "name": "users-db", "type": "RDS", "provider": "AWS", "cost_monthly": 450.0, "state": "RUNNING"},
            {"id": "s3-static-1", "name": "static-assets", "type": "S3", "provider": "AWS", "cost_monthly": 20.0, "state": "RUNNING"},
            {"id": "elb-web-1", "name": "web-lb", "type": "LoadBalancer", "provider": "AWS", "cost_monthly": 40.0, "state": "RUNNING"},
        ]
        self.opportunities = [
            {"id": "opp-rds-resize", "target_id": "rds-db-1", "type": "Oversized Database", "savings_monthly": 150.0, "risk": "MEDIUM"},
            {"id": "opp-idle-auth", "target_id": "ec2-auth-1", "type": "Underutilized Instance", "savings_monthly": 50.0, "risk": "LOW"},
        ]

    def _generate_healthcare_profile(self) -> None:
        self.applications = [
            {"id": "app-ehr", "name": "Electronic Health Records", "owner": "Helen", "team": "Clinical-IT", "criticality": "CRITICAL"},
            {"id": "app-telehealth", "name": "Telehealth Video API", "owner": "Tom", "team": "Comm-Ops", "criticality": "HIGH"},
        ]
        self.resources = [
            {"id": "rds-ehr-db", "name": "ehr-patient-db", "type": "RDS", "provider": "AWS", "cost_monthly": 2800.0, "state": "RUNNING"},
            {"id": "ec2-video-1", "name": "video-transcoder", "type": "EC2", "provider": "AWS", "cost_monthly": 600.0, "state": "RUNNING"},
            {"id": "s3-hipaa-logs", "name": "hipaa-audit-logs", "type": "S3", "provider": "AWS", "cost_monthly": 150.0, "state": "RUNNING"},
        ]
        self.opportunities = [
            {"id": "opp-ehr-db", "target_id": "rds-ehr-db", "type": "Oversized HIPAA Database", "savings_monthly": 800.0, "risk": "HIGH"},
        ]

    def _generate_manufacturing_profile(self) -> None:
        self.applications = [
            {"id": "app-iot", "name": "Factory IoT Stream", "owner": "Max", "team": "IoT-Ops", "criticality": "HIGH"},
        ]
        self.resources = [
            {"id": "ec2-iot-collector", "name": "iot-broker", "type": "EC2", "provider": "AWS", "cost_monthly": 450.0, "state": "RUNNING"},
            {"id": "dynamo-telemetry", "name": "factory-sensor-data", "type": "DynamoDB", "provider": "AWS", "cost_monthly": 1200.0, "state": "RUNNING"},
        ]
        self.opportunities = [
            {"id": "opp-dynamo-autoscaling", "target_id": "dynamo-telemetry", "type": "DynamoDB overprovisioned write capacity", "savings_monthly": 400.0, "risk": "LOW"},
        ]

    def _generate_gaming_profile(self) -> None:
        self.applications = [
            {"id": "app-matchmaker", "name": "Multiplayer Matchmaker", "owner": "Sven", "team": "NetCode", "criticality": "HIGH"},
            {"id": "app-lobby", "name": "Game Lobby API", "owner": "Elena", "team": "Backend-Services", "criticality": "MEDIUM"},
        ]
        self.resources = [
            {"id": "ec2-matchmaker-1", "name": "matchmaker-node-1", "type": "EC2", "provider": "AWS", "cost_monthly": 900.0, "state": "RUNNING"},
            {"id": "ec2-matchmaker-2", "name": "matchmaker-node-2", "type": "EC2", "provider": "AWS", "cost_monthly": 900.0, "state": "RUNNING"},
            {"id": "redis-match-cache", "name": "lobby-cache", "type": "Redis", "provider": "AWS", "cost_monthly": 300.0, "state": "RUNNING"},
        ]
        self.opportunities = [
            {"id": "opp-matchmaker-scale", "target_id": "ec2-matchmaker-2", "type": "Matchmaker scale down", "savings_monthly": 900.0, "risk": "MEDIUM"},
        ]

    def _generate_ai_profile(self) -> None:
        self.applications = [
            {"id": "app-training", "name": "LLM Model Training", "owner": "Ivan", "team": "ML-Research", "criticality": "MEDIUM"},
            {"id": "app-inference", "name": "Model Inference API", "owner": "Judy", "team": "ML-Ops", "criticality": "HIGH"},
        ]
        for i in range(5):
            self.resources.append({
                "id": f"ec2-gpu-node-{i}",
                "name": f"ml-gpu-training-{i}",
                "type": "EC2",
                "provider": "AWS",
                "cost_monthly": 4500.0,
                "state": "RUNNING"
            })
        self.opportunities = [
            {"id": "opp-gpu-scale-down", "target_id": "ec2-gpu-node-4", "type": "Idle GPU cluster node", "savings_monthly": 4500.0, "risk": "MEDIUM"},
        ]

    def _generate_saas_profile(self) -> None:
        self.applications = [
            {"id": "app-billing", "name": "Billing Service", "owner": "David", "team": "Fintech", "criticality": "HIGH"},
            {"id": "app-api", "name": "SaaS Platform API", "owner": "Emma", "team": "Platform", "criticality": "CRITICAL"},
        ]
        for i in range(15):
            self.resources.append({
                "id": f"ec2-api-{i}",
                "name": f"api-node-{i}",
                "type": "EC2",
                "provider": "AWS",
                "cost_monthly": 180.0,
                "state": "RUNNING"
            })
        self.resources.extend([
            {"id": "rds-db-replica-1", "name": "billing-replica", "type": "RDS", "provider": "AWS", "cost_monthly": 900.0, "state": "RUNNING"},
            {"id": "rds-db-primary-1", "name": "billing-primary", "type": "RDS", "provider": "AWS", "cost_monthly": 1800.0, "state": "RUNNING"},
        ])
        self.opportunities = [
            {"id": "opp-scale-api", "target_id": "ec2-api-1", "type": "Autoscaling Optimization", "savings_monthly": 800.0, "risk": "LOW"},
            {"id": "opp-db-consolidation", "target_id": "rds-db-replica-1", "type": "Unused Database Replica", "savings_monthly": 900.0, "risk": "MEDIUM"},
        ]

    def _generate_financial_profile(self) -> None:
        self.applications = [
            {"id": "app-transactions", "name": "Transaction Processing", "owner": "Karl", "team": "Core-Banking", "criticality": "CRITICAL"},
        ]
        for reg in ["us-east-1", "eu-west-1", "ap-southeast-1"]:
            self.resources.append({
                "id": f"rds-banking-{reg}",
                "name": f"banking-db-{reg}",
                "type": "RDS",
                "provider": "AWS",
                "cost_monthly": 3000.0,
                "state": "RUNNING"
            })
        self.opportunities = [
            {"id": "opp-db-banking", "target_id": "rds-banking-ap-southeast-1", "type": "Oversized compliance database", "savings_monthly": 1000.0, "risk": "HIGH"},
        ]

    def _generate_government_profile(self) -> None:
        self.applications = [
            {"id": "app-portal", "name": "Citizen Services Portal", "owner": "George", "team": "Civic-Tech", "criticality": "CRITICAL"},
        ]
        self.resources = [
            {"id": "ec2-gov-portal", "name": "citizen-portal-srv", "type": "EC2", "provider": "AWS", "cost_monthly": 600.0, "state": "RUNNING"},
            {"id": "rds-gov-db", "name": "citizen-records", "type": "RDS", "provider": "AWS", "cost_monthly": 2000.0, "state": "RUNNING"},
        ]
        self.opportunities = [
            {"id": "opp-gov-db", "target_id": "rds-gov-db", "type": "Unused read replica", "savings_monthly": 1000.0, "risk": "HIGH"},
        ]

    def _generate_media_profile(self) -> None:
        self.applications = [
            {"id": "app-streaming", "name": "VOD Video Streaming", "owner": "Rachel", "team": "Media-Delivery", "criticality": "CRITICAL"},
        ]
        self.resources = [
            {"id": "ec2-transcoder", "name": "vod-transcoder", "type": "EC2", "provider": "AWS", "cost_monthly": 1500.0, "state": "RUNNING"},
            {"id": "s3-media-bucket", "name": "vod-assets", "type": "S3", "provider": "AWS", "cost_monthly": 5000.0, "state": "RUNNING"},
        ]
        self.opportunities = [
            {"id": "opp-media-tiering", "target_id": "s3-media-bucket", "type": "S3 Intelligent-Tiering conversion", "savings_monthly": 1500.0, "risk": "LOW"},
        ]

    def _generate_retail_profile(self) -> None:
        self.applications = [
            {"id": "app-checkout", "name": "Checkout Cart Service", "owner": "Lisa", "team": "Ecom-Sales", "criticality": "CRITICAL"},
            {"id": "app-catalog", "name": "Product Catalog Service", "owner": "Max", "team": "Ecom-Ops", "criticality": "HIGH"},
        ]
        self.resources = [
            {"id": "ec2-cart-1", "name": "cart-server-1", "type": "EC2", "provider": "AWS", "cost_monthly": 200.0, "state": "RUNNING"},
            {"id": "ec2-cart-2", "name": "cart-server-2", "type": "EC2", "provider": "AWS", "cost_monthly": 200.0, "state": "RUNNING"},
            {"id": "elb-cart", "name": "cart-lb", "type": "LoadBalancer", "provider": "AWS", "cost_monthly": 50.0, "state": "RUNNING"},
        ]
        self.opportunities = [
            {"id": "opp-cart-consolidation", "target_id": "ec2-cart-2", "type": "Idle secondary web node", "savings_monthly": 200.0, "risk": "LOW"},
        ]
