"""
Enterprise scenario profile implementations for all 7 business domains:
1. SaaS Platform
2. Banking & Financial Services
3. E-commerce & Retail
4. AI Research & Model Labs
5. Startup (Lean & High Growth)
6. Healthcare & Clinical Informatics
7. Gaming & Multiplayer Fleet

Generates fully connected, referentially consistent topologies scaling to 100+, 500+, 1000+ resources.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Type

from simulator.ground_truth import GroundTruthAction, GroundTruthStrategy
from simulator.models import (
    ActionType,
    CloudAccount,
    CloudProvider,
    ComputeState,
    CriticalityLevel,
    DatabaseState,
    IncidentSeverity,
    SimulatedApplication,
    SimulatedCompute,
    SimulatedDatabase,
    SimulatedDependencyEdge,
    SimulatedHistoricalEvent,
    SimulatedIncident,
    SimulatedK8sCluster,
    SimulatedLoadBalancer,
    SimulatedSecurityGroup,
    SimulatedService,
    SimulatedStorage,
    SimulatedSubnet,
    SimulatedTelemetryPoint,
    SimulatedVPC,
    SimulationScale,
)
from simulator.scenarios.base import BaseScenarioBuilder, ScenarioContext


# ══════════════════════════════════════════════════════════════════
# Helper Generator Functions
# ══════════════════════════════════════════════════════════════════

def _create_telemetry(target_id: str, is_idle: bool, is_hot: bool, rng) -> List[SimulatedTelemetryPoint]:
    """Generate 5 historical telemetry snapshots."""
    points = []
    now = datetime.now(timezone.utc)
    for i in range(5):
        t = now - timedelta(minutes=(5 - i) * 5)
        if is_idle:
            cpu = rng.uniform(2.0, 8.0)
            mem = rng.uniform(15.0, 25.0)
            lat = rng.uniform(10.0, 25.0)
            err = 0.0
        elif is_hot:
            cpu = rng.uniform(82.0, 96.0)
            mem = rng.uniform(85.0, 94.0)
            lat = rng.uniform(150.0, 350.0)
            err = rng.uniform(0.01, 0.04)
        else:
            cpu = rng.uniform(35.0, 65.0)
            mem = rng.uniform(45.0, 65.0)
            lat = rng.uniform(30.0, 65.0)
            err = rng.uniform(0.0001, 0.001)

        points.append(
            SimulatedTelemetryPoint(
                target_id=target_id,
                timestamp=t,
                cpu_percent=round(cpu, 1),
                memory_percent=round(mem, 1),
                network_in_mbps=round(rng.uniform(10.0, 100.0), 1),
                network_out_mbps=round(rng.uniform(20.0, 200.0), 1),
                latency_ms=round(lat, 1),
                error_rate=round(err, 4),
            )
        )
    return points


# ══════════════════════════════════════════════════════════════════
# 1. SaaS Enterprise Scenario
# ══════════════════════════════════════════════════════════════════

class SaaSScenarioBuilder(BaseScenarioBuilder):
    """Multi-tenant B2B SaaS platform: Web, API, Auth, Billing, Background Workers, Aurora, Redis."""

    def build(self) -> ScenarioContext:
        mult = self.get_scale_multiplier()
        acct = CloudAccount(
            account_id="acct-saas-prod-100",
            name="CloudFlow SaaS Enterprise",
            provider=CloudProvider.AWS,
            billing_account_id="ba-987654",
            tags={"Organization": "CloudFlow", "Domain": "SaaS"},
        )
        ctx = ScenarioContext(profile_name="SaaS", scale=self.scale, seed=self.seed, account=acct)

        # 1. Network: VPCs & Subnets
        vpc = SimulatedVPC(
            vpc_id="vpc-saas-prod",
            account_id=acct.account_id,
            region="us-east-1",
            name="saas-production-vpc",
            cidr_block="10.100.0.0/16",
        )
        ctx.vpcs.append(vpc)

        sub_pub = SimulatedSubnet(
            subnet_id="sub-saas-pub-1",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.100.1.0/24",
            tier="public",
        )
        sub_priv = SimulatedSubnet(
            subnet_id="sub-saas-priv-1",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.100.10.0/24",
            tier="private",
        )
        sub_db = SimulatedSubnet(
            subnet_id="sub-saas-db-1",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.100.20.0/24",
            tier="database",
        )
        ctx.subnets.extend([sub_pub, sub_priv, sub_db])

        sg_web = SimulatedSecurityGroup(sg_id="sg-saas-web", vpc_id=vpc.vpc_id, name="saas-web-sg", description="Web ALB")
        sg_app = SimulatedSecurityGroup(sg_id="sg-saas-app", vpc_id=vpc.vpc_id, name="saas-app-sg", description="App Tier")
        sg_db = SimulatedSecurityGroup(sg_id="sg-saas-db", vpc_id=vpc.vpc_id, name="saas-db-sg", description="DB Tier")
        ctx.security_groups.extend([sg_web, sg_app, sg_db])

        # 2. Databases & Storage
        db_aurora = SimulatedDatabase(
            database_id="db-saas-aurora-cluster",
            name="saas-core-aurora",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_db.subnet_id],
            engine="aurora-postgresql",
            instance_class="db.r6g.2xlarge",
            allocated_storage_gib=1000,
            endpoint="saas-core.cluster.us-east-1.rds.amazonaws.com",
            monthly_cost_usd=1450.0,
        )
        db_redis = SimulatedDatabase(
            database_id="cache-saas-redis",
            name="saas-session-redis",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_priv.subnet_id],
            engine="redis",
            instance_class="cache.m6g.xlarge",
            allocated_storage_gib=50,
            port=6379,
            endpoint="saas-cache.us-east-1.cache.amazonaws.com",
            monthly_cost_usd=380.0,
        )
        # An oversized, underutilized staging DB that is safe to rightsize
        db_staging = SimulatedDatabase(
            database_id="db-saas-staging",
            name="saas-staging-db",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_db.subnet_id],
            engine="postgres",
            instance_class="db.m5.4xlarge",
            allocated_storage_gib=500,
            endpoint="staging.us-east-1.rds.amazonaws.com",
            monthly_cost_usd=980.0,
        )
        ctx.databases.extend([db_aurora, db_redis, db_staging])

        s3_assets = SimulatedStorage(
            storage_id="s3-saas-customer-assets",
            name="saas-customer-assets-prod",
            account_id=acct.account_id,
            region="us-east-1",
            size_gib=12500.0,
            object_count=450000,
            monthly_cost_usd=287.50,
        )
        ctx.storage.append(s3_assets)

        # 3. Compute & Kubernetes Clusters
        k8s = SimulatedK8sCluster(
            cluster_id="eks-saas-prod",
            name="saas-prod-cluster",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_priv.subnet_id],
            namespaces=["production", "monitoring", "ingress"],
        )
        ctx.k8s_clusters.append(k8s)

        # Generate compute nodes (scale dynamically: 12 base * multiplier)
        num_web = 6 * mult
        num_workers = 6 * mult
        alb_targets = []

        for i in range(1, num_web + 1):
            inst_id = f"ec2-saas-web-{i:03d}"
            inst = SimulatedCompute(
                instance_id=inst_id,
                name=f"saas-web-server-{i}",
                account_id=acct.account_id,
                region="us-east-1",
                vpc_id=vpc.vpc_id,
                subnet_id=sub_priv.subnet_id,
                security_group_ids=[sg_app.sg_id],
                instance_type="c6g.xlarge",
                vcpu=4,
                memory_gib=8.0,
                monthly_cost_usd=125.0,
                hourly_rate_usd=0.17,
                private_ip=f"10.100.10.{10 + i}",
                app_id="app-saas-web",
                service_id="svc-web-api",
            )
            ctx.compute.append(inst)
            alb_targets.append(inst_id)
            ctx.telemetry[inst_id] = _create_telemetry(inst_id, is_idle=False, is_hot=(i == 1), rng=self.rng)

        # Background worker instances (some underutilized)
        worker_ids = []
        for i in range(1, num_workers + 1):
            inst_id = f"ec2-saas-worker-{i:03d}"
            is_idle = (i % 2 == 0)  # half are idle/oversized
            inst = SimulatedCompute(
                instance_id=inst_id,
                name=f"saas-bg-worker-{i}",
                account_id=acct.account_id,
                region="us-east-1",
                vpc_id=vpc.vpc_id,
                subnet_id=sub_priv.subnet_id,
                security_group_ids=[sg_app.sg_id],
                instance_type="m5.2xlarge" if is_idle else "m5.large",
                vcpu=8 if is_idle else 2,
                memory_gib=32.0 if is_idle else 8.0,
                monthly_cost_usd=280.0 if is_idle else 70.0,
                hourly_rate_usd=0.38 if is_idle else 0.096,
                private_ip=f"10.100.10.{100 + i}",
                app_id="app-saas-billing",
                service_id="svc-billing-engine",
            )
            ctx.compute.append(inst)
            worker_ids.append(inst_id)
            ctx.telemetry[inst_id] = _create_telemetry(inst_id, is_idle=is_idle, is_hot=False, rng=self.rng)

            # Register Ground Truth for Idle Workers: Safe to rightsize or stop
            if is_idle:
                ctx.ground_truth.register_action(
                    GroundTruthAction(
                        action_id=f"gt-saas-worker-rightsize-{i}",
                        target_id=inst_id,
                        action_type=ActionType.RIGHTSIZE,
                        is_safe=True,
                        reason="Worker CPU < 5% during last 7 days. Downsizing from m5.2xlarge to m5.large is 100% safe.",
                        expected_savings_monthly_usd=210.0,
                        expected_risk="LOW",
                        expected_outcome="SUCCESS",
                    )
                )

        # 4. Load Balancers
        alb = SimulatedLoadBalancer(
            load_balancer_id="alb-saas-ingress",
            name="saas-ingress-alb",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_pub.subnet_id],
            dns_name="api.cloudflow.io",
            target_compute_ids=alb_targets,
            monthly_cost_usd=42.0,
        )
        ctx.load_balancers.append(alb)

        # 5. Applications & Microservices
        svc_api = SimulatedService(
            service_id="svc-web-api",
            app_id="app-saas-web",
            name="Core Platform API",
            tier="api",
            compute_ids=alb_targets,
            database_ids=[db_aurora.database_id, db_redis.database_id],
        )
        svc_billing = SimulatedService(
            service_id="svc-billing-engine",
            app_id="app-saas-billing",
            name="Subscription Billing",
            tier="worker",
            compute_ids=worker_ids,
            database_ids=[db_aurora.database_id],
        )
        app_web = SimulatedApplication(
            app_id="app-saas-web",
            name="CloudFlow Core Application",
            description="Tenant API and frontend gateway",
            criticality=CriticalityLevel.TIER_1_MISSION_CRITICAL,
            owner_team="Platform Engineering",
            tech_lead="Sarah Chen",
            services=[svc_api],
        )
        app_billing = SimulatedApplication(
            app_id="app-saas-billing",
            name="Billing Engine",
            description="Recurring subscriptions and invoices",
            criticality=CriticalityLevel.TIER_2_BUSINESS_IMPORTANT,
            owner_team="Billing-Ops",
            tech_lead="Marcus Vance",
            services=[svc_billing],
        )
        ctx.applications.extend([app_web, app_billing])

        # Dependencies
        ctx.dependencies.append(
            SimulatedDependencyEdge(
                edge_id="edge-alb-web",
                source_id=alb.load_balancer_id,
                source_type="load_balancer",
                target_id=alb_targets[0],
                target_type="compute",
                relationship="routes_to",
            )
        )
        ctx.dependencies.append(
            SimulatedDependencyEdge(
                edge_id="edge-api-aurora",
                source_id=alb_targets[0],
                source_type="compute",
                target_id=db_aurora.database_id,
                target_type="database",
                relationship="reads_writes",
            )
        )
        ctx.dependencies.append(
            SimulatedDependencyEdge(
                edge_id="edge-api-redis",
                source_id=alb_targets[0],
                source_type="compute",
                target_id=db_redis.database_id,
                target_type="database",
                relationship="reads_from",
            )
        )

        # Ground Truth: Dangerous Action (Terminating Aurora Primary)
        ctx.ground_truth.register_action(
            GroundTruthAction(
                action_id="gt-unsafe-aurora-term",
                target_id=db_aurora.database_id,
                action_type=ActionType.TERMINATE,
                is_safe=False,
                reason="CRITICAL OUTAGE: Terminating Aurora primary will take down entire SaaS platform and violate customer SLAs.",
                expected_savings_monthly_usd=1450.0,
                expected_risk="CRITICAL",
                blast_radius_resource_ids=alb_targets + worker_ids,
                expected_outcome="OUTAGE",
            )
        )
        # Ground Truth: Safe Action (Rightsizing Staging DB)
        ctx.ground_truth.register_action(
            GroundTruthAction(
                action_id="gt-safe-staging-rightsize",
                target_id=db_staging.database_id,
                action_type=ActionType.RIGHTSIZE,
                is_safe=True,
                reason="Staging DB is severely overprovisioned (db.m5.4xlarge with 2% CPU). Rightsizing to db.m5.large saves $750/mo.",
                expected_savings_monthly_usd=750.0,
                expected_risk="LOW",
                expected_outcome="SUCCESS",
            )
        )

        self.validate_consistency(ctx)
        return ctx


# ══════════════════════════════════════════════════════════════════
# 2. Banking & Financial Services Scenario
# ══════════════════════════════════════════════════════════════════

class BankingScenarioBuilder(BaseScenarioBuilder):
    """Tier-1 Core Banking: PCI-DSS, ledger, fraud detection, multi-region active-active."""

    def build(self) -> ScenarioContext:
        mult = self.get_scale_multiplier()
        acct = CloudAccount(
            account_id="acct-bank-fin-999",
            name="Apex Financial Core Banking",
            provider=CloudProvider.AWS,
            billing_account_id="ba-fin-101010",
            tags={"Compliance": "PCI-DSS", "Domain": "Banking"},
        )
        ctx = ScenarioContext(profile_name="Banking", scale=self.scale, seed=self.seed, account=acct)

        vpc = SimulatedVPC(
            vpc_id="vpc-bank-prod",
            account_id=acct.account_id,
            region="us-east-1",
            name="banking-core-vpc",
            cidr_block="10.200.0.0/16",
        )
        ctx.vpcs.append(vpc)

        sub_pci = SimulatedSubnet(
            subnet_id="sub-bank-pci-1",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.200.1.0/24",
            tier="private",
            tags={"Classification": "PCI-Scoped"},
        )
        sub_db = SimulatedSubnet(
            subnet_id="sub-bank-db-1",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.200.10.0/24",
            tier="database",
        )
        ctx.subnets.extend([sub_pci, sub_db])

        sg_core = SimulatedSecurityGroup(sg_id="sg-bank-core", vpc_id=vpc.vpc_id, name="bank-core-sg", description="Core Ledger SG")
        ctx.security_groups.append(sg_core)

        # Core Ledger DB
        db_ledger = SimulatedDatabase(
            database_id="db-bank-ledger-primary",
            name="core-ledger-postgres",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_db.subnet_id],
            engine="postgres",
            instance_class="db.r6i.8xlarge",
            allocated_storage_gib=4000,
            multi_az=True,
            endpoint="ledger-prod.bank.internal",
            monthly_cost_usd=5200.0,
        )
        ctx.databases.append(db_ledger)

        # Audit logs bucket
        s3_audit = SimulatedStorage(
            storage_id="s3-bank-compliance-audit",
            name="bank-immutable-audit-records",
            account_id=acct.account_id,
            region="us-east-1",
            size_gib=45000.0,
            object_count=1800000,
            storage_class="GLACIER",
            monthly_cost_usd=450.0,
        )
        ctx.storage.append(s3_audit)

        # Transaction compute nodes
        num_nodes = 8 * mult
        node_ids = []
        for i in range(1, num_nodes + 1):
            inst_id = f"ec2-bank-txn-{i:03d}"
            inst = SimulatedCompute(
                instance_id=inst_id,
                name=f"bank-txn-processor-{i}",
                account_id=acct.account_id,
                region="us-east-1",
                vpc_id=vpc.vpc_id,
                subnet_id=sub_pci.subnet_id,
                security_group_ids=[sg_core.sg_id],
                instance_type="c6i.4xlarge",
                vcpu=16,
                memory_gib=32.0,
                monthly_cost_usd=495.0,
                hourly_rate_usd=0.68,
                private_ip=f"10.200.1.{10 + i}",
                app_id="app-bank-ledger",
                service_id="svc-ledger-engine",
            )
            ctx.compute.append(inst)
            node_ids.append(inst_id)
            ctx.telemetry[inst_id] = _create_telemetry(inst_id, is_idle=False, is_hot=False, rng=self.rng)

        # Application
        svc_ledger = SimulatedService(
            service_id="svc-ledger-engine",
            app_id="app-bank-ledger",
            name="Transaction Settlement",
            tier="api",
            compute_ids=node_ids,
            database_ids=[db_ledger.database_id],
        )
        app_bank = SimulatedApplication(
            app_id="app-bank-ledger",
            name="Apex Core Banking Ledger",
            description="Real-time transaction posting & settlement",
            criticality=CriticalityLevel.TIER_1_MISSION_CRITICAL,
            owner_team="FinTech Core SRE",
            tech_lead="David Miller",
            sla_target_percent=99.999,
            services=[svc_ledger],
        )
        ctx.applications.append(app_bank)

        # Ground Truth: Terminating core ledger DB is catastrophic
        ctx.ground_truth.register_action(
            GroundTruthAction(
                action_id="gt-bank-ledger-unsafe",
                target_id=db_ledger.database_id,
                action_type=ActionType.TERMINATE,
                is_safe=False,
                reason="SEV-1 CATASTROPHIC: Deleting Core Ledger results in massive financial data loss and regulatory fines.",
                expected_savings_monthly_usd=5200.0,
                expected_risk="CRITICAL",
                blast_radius_resource_ids=node_ids,
                expected_outcome="DATA_LOSS",
            )
        )
        # Safe reservation action on predictable nodes
        ctx.ground_truth.register_action(
            GroundTruthAction(
                action_id="gt-bank-reserved-safe",
                target_id=node_ids[0],
                action_type=ActionType.APPLY_RESERVATION,
                is_safe=True,
                reason="Core transaction nodes run 24/7. Applying 1-year Savings Plan saves 38% with zero risk.",
                expected_savings_monthly_usd=188.0,
                expected_risk="LOW",
                expected_outcome="SUCCESS",
            )
        )

        self.validate_consistency(ctx)
        return ctx


# ══════════════════════════════════════════════════════════════════
# 3. E-commerce Scenario
# ══════════════════════════════════════════════════════════════════

class EcommerceScenarioBuilder(BaseScenarioBuilder):
    """High-traffic Retail E-commerce: CDN, Storefront, Cart, Checkout, DynamoDB, Redis."""

    def build(self) -> ScenarioContext:
        mult = self.get_scale_multiplier()
        acct = CloudAccount(
            account_id="acct-ecom-prod-555",
            name="MegaStore Retail Global",
            provider=CloudProvider.AWS,
            billing_account_id="ba-retail-555",
            tags={"Industry": "Retail", "Domain": "E-commerce"},
        )
        ctx = ScenarioContext(profile_name="E-commerce", scale=self.scale, seed=self.seed, account=acct)

        vpc = SimulatedVPC(
            vpc_id="vpc-ecom-prod",
            account_id=acct.account_id,
            region="us-west-2",
            name="ecom-store-vpc",
            cidr_block="10.150.0.0/16",
        )
        ctx.vpcs.append(vpc)

        sub_app = SimulatedSubnet(
            subnet_id="sub-ecom-app-1",
            vpc_id=vpc.vpc_id,
            region="us-west-2",
            availability_zone="us-west-2a",
            cidr_block="10.150.1.0/24",
            tier="private",
        )
        sub_db = SimulatedSubnet(
            subnet_id="sub-ecom-db-1",
            vpc_id=vpc.vpc_id,
            region="us-west-2",
            availability_zone="us-west-2a",
            cidr_block="10.150.10.0/24",
            tier="database",
        )
        ctx.subnets.extend([sub_app, sub_db])

        sg_ecom = SimulatedSecurityGroup(sg_id="sg-ecom-app", vpc_id=vpc.vpc_id, name="ecom-app-sg", description="Ecom App SG")
        ctx.security_groups.append(sg_ecom)

        db_cart = SimulatedDatabase(
            database_id="cache-ecom-redis",
            name="ecom-cart-session-cache",
            account_id=acct.account_id,
            region="us-west-2",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_db.subnet_id],
            engine="redis",
            instance_class="cache.r6g.xlarge",
            allocated_storage_gib=100,
            port=6379,
            endpoint="cart-redis.ecom.internal",
            monthly_cost_usd=420.0,
        )
        db_catalog = SimulatedDatabase(
            database_id="db-ecom-catalog",
            name="ecom-product-catalog",
            account_id=acct.account_id,
            region="us-west-2",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_db.subnet_id],
            engine="aurora-postgresql",
            instance_class="db.r6g.xlarge",
            allocated_storage_gib=800,
            endpoint="catalog.ecom.internal",
            monthly_cost_usd=850.0,
        )
        ctx.databases.extend([db_cart, db_catalog])

        # Cart & Checkout nodes
        num_nodes = 10 * mult
        cart_nodes = []
        for i in range(1, num_nodes + 1):
            inst_id = f"ec2-ecom-cart-{i:03d}"
            inst = SimulatedCompute(
                instance_id=inst_id,
                name=f"ecom-cart-svc-{i}",
                account_id=acct.account_id,
                region="us-west-2",
                vpc_id=vpc.vpc_id,
                subnet_id=sub_app.subnet_id,
                security_group_ids=[sg_ecom.sg_id],
                instance_type="m6i.xlarge",
                vcpu=4,
                memory_gib=16.0,
                monthly_cost_usd=140.0,
                hourly_rate_usd=0.192,
                private_ip=f"10.150.1.{10 + i}",
                app_id="app-ecom-cart",
                service_id="svc-cart",
            )
            ctx.compute.append(inst)
            cart_nodes.append(inst_id)
            ctx.telemetry[inst_id] = _create_telemetry(inst_id, is_idle=False, is_hot=(i == 1), rng=self.rng)

        svc_cart = SimulatedService(
            service_id="svc-cart",
            app_id="app-ecom-cart",
            name="Shopping Cart Service",
            tier="api",
            compute_ids=cart_nodes,
            database_ids=[db_cart.database_id, db_catalog.database_id],
        )
        app_ecom = SimulatedApplication(
            app_id="app-ecom-cart",
            name="MegaStore Checkout & Cart",
            description="Active customer carts and catalog search",
            criticality=CriticalityLevel.TIER_1_MISSION_CRITICAL,
            owner_team="Checkout Engineering",
            tech_lead="Jessica Wu",
            services=[svc_cart],
        )
        ctx.applications.append(app_ecom)

        # Ground Truth: Stopping Cart Redis will cause cart loss
        ctx.ground_truth.register_action(
            GroundTruthAction(
                action_id="gt-ecom-redis-unsafe",
                target_id=db_cart.database_id,
                action_type=ActionType.STOP,
                is_safe=False,
                reason="UNSAFE: Stopping cart Redis cache will instantly wipe millions of dollars in active shopping carts.",
                expected_savings_monthly_usd=420.0,
                expected_risk="CRITICAL",
                expected_outcome="OUTAGE",
            )
        )

        self.validate_consistency(ctx)
        return ctx


# ══════════════════════════════════════════════════════════════════
# 4. AI Research & Lab Scenario
# ══════════════════════════════════════════════════════════════════

class AIResearchScenarioBuilder(BaseScenarioBuilder):
    """AI Research: Multi-node GPU training clusters, MLflow, Ray clusters, S3 datasets."""

    def build(self) -> ScenarioContext:
        mult = self.get_scale_multiplier()
        acct = CloudAccount(
            account_id="acct-ai-lab-777",
            name="DeepScale Intelligence Lab",
            provider=CloudProvider.AWS,
            billing_account_id="ba-ai-777",
            tags={"Domain": "AI Research"},
        )
        ctx = ScenarioContext(profile_name="AI Research", scale=self.scale, seed=self.seed, account=acct)

        vpc = SimulatedVPC(
            vpc_id="vpc-ai-lab",
            account_id=acct.account_id,
            region="us-east-1",
            name="ai-research-vpc",
            cidr_block="10.250.0.0/16",
        )
        ctx.vpcs.append(vpc)

        sub_gpu = SimulatedSubnet(
            subnet_id="sub-ai-gpu-1",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.250.1.0/24",
            tier="private",
        )
        sub_head = SimulatedSubnet(
            subnet_id="sub-ai-head-1",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1b",
            cidr_block="10.250.2.0/24",
            tier="private",
        )
        ctx.subnets.extend([sub_gpu, sub_head])

        sg_gpu = SimulatedSecurityGroup(sg_id="sg-ai-gpu", vpc_id=vpc.vpc_id, name="ai-gpu-sg", description="GPU Training Fleet")
        sg_head = SimulatedSecurityGroup(sg_id="sg-ai-head", vpc_id=vpc.vpc_id, name="ai-head-sg", description="Ray/Slurm Cluster Head")
        ctx.security_groups.extend([sg_gpu, sg_head])

        s3_weights = SimulatedStorage(
            storage_id="s3-ai-checkpoints",
            name="deepscale-model-checkpoints",
            account_id=acct.account_id,
            region="us-east-1",
            size_gib=85000.0,
            object_count=12000,
            monthly_cost_usd=1955.0,
        )
        s3_datasets = SimulatedStorage(
            storage_id="s3-ai-datasets",
            name="deepscale-curated-pretraining-corpus",
            account_id=acct.account_id,
            region="us-east-1",
            size_gib=180000.0,
            object_count=45000,
            monthly_cost_usd=4140.0,
        )
        ctx.storage.extend([s3_weights, s3_datasets])

        db_mlflow = SimulatedDatabase(
            database_id="db-ai-mlflow-pg",
            name="mlflow-experiment-tracking",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_head.subnet_id],
            engine="postgres",
            instance_class="db.r6g.xlarge",
            allocated_storage_gib=500,
            endpoint="mlflow-db.ai.internal",
            monthly_cost_usd=320.0,
        )
        ctx.databases.append(db_mlflow)

        # Head orchestration node
        head_inst = SimulatedCompute(
            instance_id="ec2-ai-head-001",
            name="ray-cluster-head",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_id=sub_head.subnet_id,
            security_group_ids=[sg_head.sg_id],
            instance_type="c6i.4xlarge",
            vcpu=16,
            memory_gib=32.0,
            monthly_cost_usd=495.0,
            hourly_rate_usd=0.68,
            private_ip="10.250.2.10",
            app_id="app-ai-training",
            service_id="svc-llm-train",
        )
        ctx.compute.append(head_inst)
        ctx.telemetry[head_inst.instance_id] = _create_telemetry(head_inst.instance_id, is_idle=False, is_hot=False, rng=self.rng)

        # High Cost GPU Nodes (p4d.24xlarge: ~$32/hr => ~$23,000/mo each)
        num_gpus = 4 * mult
        gpu_nodes = [head_inst.instance_id]
        for i in range(1, num_gpus + 1):
            inst_id = f"ec2-gpu-node-{i:03d}"
            # Even nodes are idle experiments left running over the weekend!
            is_idle = (i % 2 == 0)
            inst = SimulatedCompute(
                instance_id=inst_id,
                name=f"gpu-training-box-{i}",
                account_id=acct.account_id,
                region="us-east-1",
                vpc_id=vpc.vpc_id,
                subnet_id=sub_gpu.subnet_id,
                security_group_ids=[sg_gpu.sg_id],
                instance_type="p4d.24xlarge",
                vcpu=96,
                memory_gib=1152.0,
                monthly_cost_usd=23500.0,
                hourly_rate_usd=32.77,
                private_ip=f"10.250.1.{20 + i}",
                app_id="app-ai-training",
                service_id="svc-llm-train",
            )
            ctx.compute.append(inst)
            gpu_nodes.append(inst_id)
            ctx.telemetry[inst_id] = _create_telemetry(inst_id, is_idle=is_idle, is_hot=(not is_idle), rng=self.rng)

            # Ground truth: Stopping idle multi-thousand dollar GPU nodes is a huge safe win!
            if is_idle:
                ctx.ground_truth.register_action(
                    GroundTruthAction(
                        action_id=f"gt-ai-stop-idle-gpu-{i}",
                        target_id=inst_id,
                        action_type=ActionType.STOP,
                        is_safe=True,
                        reason="Training run completed 48 hours ago. GPU utilization 0%. Stopping instance saves $23,500/mo.",
                        expected_savings_monthly_usd=23500.0,
                        expected_risk="LOW",
                        expected_outcome="SUCCESS",
                    )
                )

        svc_train = SimulatedService(
            service_id="svc-llm-train",
            app_id="app-ai-training",
            name="LLM Distributed Pre-training",
            tier="worker",
            compute_ids=gpu_nodes,
            database_ids=[db_mlflow.database_id],
        )
        app_ai = SimulatedApplication(
            app_id="app-ai-training",
            name="DeepScale Foundation Model",
            description="70B parameter model training pipeline",
            criticality=CriticalityLevel.TIER_2_BUSINESS_IMPORTANT,
            owner_team="Research Science",
            tech_lead="Dr. Elena Rostov",
            services=[svc_train],
        )
        ctx.applications.append(app_ai)

        self.validate_consistency(ctx)
        return ctx


# ══════════════════════════════════════════════════════════════════
# 5. Startup Scenario
# ══════════════════════════════════════════════════════════════════

class StartupScenarioBuilder(BaseScenarioBuilder):
    """Early Stage Startup: Single-region lean infrastructure, Postgres, S3, Web server."""

    def build(self) -> ScenarioContext:
        acct = CloudAccount(
            account_id="acct-startup-123",
            name="LaunchPad Early Startup",
            provider=CloudProvider.AWS,
            billing_account_id="ba-startup-123",
        )
        ctx = ScenarioContext(profile_name="Startup", scale=self.scale, seed=self.seed, account=acct)

        vpc = SimulatedVPC(
            vpc_id="vpc-startup",
            account_id=acct.account_id,
            region="us-east-1",
            name="startup-vpc",
            cidr_block="10.0.0.0/16",
        )
        ctx.vpcs.append(vpc)

        sub_priv = SimulatedSubnet(
            subnet_id="sub-startup-priv",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.0.1.0/24",
            tier="private",
        )
        sub_pub = SimulatedSubnet(
            subnet_id="sub-startup-pub",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1b",
            cidr_block="10.0.2.0/24",
            tier="public",
        )
        ctx.subnets.extend([sub_priv, sub_pub])

        sg_app = SimulatedSecurityGroup(sg_id="sg-startup-app", vpc_id=vpc.vpc_id, name="startup-app-sg", description="Startup App SG")
        sg_alb = SimulatedSecurityGroup(sg_id="sg-startup-alb", vpc_id=vpc.vpc_id, name="startup-alb-sg", description="Startup Public ALB SG")
        ctx.security_groups.extend([sg_app, sg_alb])

        s3_assets = SimulatedStorage(
            storage_id="s3-startup-assets",
            name="startup-launchpad-assets",
            account_id=acct.account_id,
            region="us-east-1",
            size_gib=350.0,
            object_count=4500,
            monthly_cost_usd=8.05,
        )
        ctx.storage.append(s3_assets)

        db_pg = SimulatedDatabase(
            database_id="db-startup-postgres",
            name="startup-core-pg",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_priv.subnet_id],
            engine="postgres",
            instance_class="db.t4g.large",
            allocated_storage_gib=100,
            endpoint="pg.startup.internal",
            monthly_cost_usd=95.0,
        )
        db_redis = SimulatedDatabase(
            database_id="cache-startup-redis",
            name="startup-session-cache",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_priv.subnet_id],
            engine="redis",
            instance_class="cache.t4g.micro",
            allocated_storage_gib=10,
            endpoint="redis.startup.internal",
            monthly_cost_usd=16.0,
        )
        ctx.databases.extend([db_pg, db_redis])

        # Web compute
        num_nodes = 6 * self.get_scale_multiplier()
        comp_ids = []
        for i in range(1, num_nodes + 1):
            inst_id = f"ec2-startup-app-{i:03d}"
            inst = SimulatedCompute(
                instance_id=inst_id,
                name=f"startup-app-{i}",
                account_id=acct.account_id,
                region="us-east-1",
                vpc_id=vpc.vpc_id,
                subnet_id=sub_priv.subnet_id,
                security_group_ids=[sg_app.sg_id],
                instance_type="t4g.medium",
                vcpu=2,
                memory_gib=4.0,
                monthly_cost_usd=30.0,
                hourly_rate_usd=0.0416,
                private_ip=f"10.0.1.{10 + i}",
                app_id="app-startup",
                service_id="svc-startup-web",
            )
            ctx.compute.append(inst)
            comp_ids.append(inst_id)
            ctx.telemetry[inst_id] = _create_telemetry(inst_id, is_idle=(i > 2), is_hot=False, rng=self.rng)

        alb = SimulatedLoadBalancer(
            load_balancer_id="alb-startup-ingress",
            name="startup-ingress-alb",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_pub.subnet_id],
            dns_name="app.startup-launchpad.io",
            target_compute_ids=comp_ids,
            monthly_cost_usd=24.0,
        )
        ctx.load_balancers.append(alb)

        svc = SimulatedService(
            service_id="svc-startup-web",
            app_id="app-startup",
            name="Startup Web App",
            tier="web",
            compute_ids=comp_ids,
            database_ids=[db_pg.database_id, db_redis.database_id],
        )
        app = SimulatedApplication(
            app_id="app-startup",
            name="LaunchPad Web",
            description="Core startup SaaS app",
            criticality=CriticalityLevel.TIER_2_BUSINESS_IMPORTANT,
            owner_team="Founders",
            tech_lead="Bob Founder",
            services=[svc],
        )
        ctx.applications.append(app)

        self.validate_consistency(ctx)
        return ctx


# ══════════════════════════════════════════════════════════════════
# 6. Healthcare Scenario
# ══════════════════════════════════════════════════════════════════

class HealthcareScenarioBuilder(BaseScenarioBuilder):
    """Healthcare Provider: Electronic Health Records (EHR), HIPAA compliance, Telehealth."""

    def build(self) -> ScenarioContext:
        acct = CloudAccount(
            account_id="acct-health-999",
            name="CareGrid Health Systems",
            provider=CloudProvider.AWS,
            billing_account_id="ba-health-999",
            tags={"Compliance": "HIPAA", "Domain": "Healthcare"},
        )
        ctx = ScenarioContext(profile_name="Healthcare", scale=self.scale, seed=self.seed, account=acct)

        vpc = SimulatedVPC(
            vpc_id="vpc-health-prod",
            account_id=acct.account_id,
            region="us-east-1",
            name="ehr-hipaa-vpc",
            cidr_block="10.120.0.0/16",
        )
        ctx.vpcs.append(vpc)

        sub_db = SimulatedSubnet(
            subnet_id="sub-health-db",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.120.10.0/24",
            tier="database",
        )
        sub_app = SimulatedSubnet(
            subnet_id="sub-health-app",
            vpc_id=vpc.vpc_id,
            region="us-east-1",
            availability_zone="us-east-1a",
            cidr_block="10.120.1.0/24",
            tier="private",
        )
        ctx.subnets.extend([sub_db, sub_app])

        sg = SimulatedSecurityGroup(sg_id="sg-health", vpc_id=vpc.vpc_id, name="health-sg", description="HIPAA SG")
        ctx.security_groups.append(sg)

        db_ehr = SimulatedDatabase(
            database_id="db-health-ehr-primary",
            name="caregrid-ehr-postgres",
            account_id=acct.account_id,
            region="us-east-1",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_db.subnet_id],
            engine="postgres",
            instance_class="db.r5.4xlarge",
            allocated_storage_gib=2000,
            endpoint="ehr.caregrid.internal",
            monthly_cost_usd=2800.0,
        )
        ctx.databases.append(db_ehr)

        num_nodes = 6 * self.get_scale_multiplier()
        comp_ids = []
        for i in range(1, num_nodes + 1):
            inst_id = f"ec2-health-ehr-{i:03d}"
            inst = SimulatedCompute(
                instance_id=inst_id,
                name=f"caregrid-ehr-api-{i}",
                account_id=acct.account_id,
                region="us-east-1",
                vpc_id=vpc.vpc_id,
                subnet_id=sub_app.subnet_id,
                security_group_ids=[sg.sg_id],
                instance_type="m5.xlarge",
                vcpu=4,
                memory_gib=16.0,
                monthly_cost_usd=140.0,
                hourly_rate_usd=0.192,
                private_ip=f"10.120.1.{10 + i}",
                app_id="app-health-ehr",
                service_id="svc-ehr-api",
            )
            ctx.compute.append(inst)
            comp_ids.append(inst_id)
            ctx.telemetry[inst_id] = _create_telemetry(inst_id, is_idle=False, is_hot=False, rng=self.rng)

        svc_ehr = SimulatedService(
            service_id="svc-ehr-api",
            app_id="app-health-ehr",
            name="Clinical EHR Gateway",
            tier="api",
            compute_ids=comp_ids,
            database_ids=[db_ehr.database_id],
        )
        app_ehr = SimulatedApplication(
            app_id="app-health-ehr",
            name="CareGrid Patient Portal & EHR",
            description="Patient health records and telemetry",
            criticality=CriticalityLevel.TIER_1_MISSION_CRITICAL,
            owner_team="Clinical Informatics",
            tech_lead="Dr. Michael Chang",
            services=[svc_ehr],
        )
        ctx.applications.append(app_ehr)

        # Ground Truth: Modifying EHR primary is unsafe without maintenance signoff
        ctx.ground_truth.register_action(
            GroundTruthAction(
                action_id="gt-health-ehr-unsafe",
                target_id=db_ehr.database_id,
                action_type=ActionType.TERMINATE,
                is_safe=False,
                reason="HIPAA VIOLATION & OUTAGE: Cannot terminate primary patient EHR database.",
                expected_savings_monthly_usd=2800.0,
                expected_risk="CRITICAL",
                expected_outcome="OUTAGE",
            )
        )

        self.validate_consistency(ctx)
        return ctx


# ══════════════════════════════════════════════════════════════════
# 7. Gaming Scenario
# ══════════════════════════════════════════════════════════════════

class GamingScenarioBuilder(BaseScenarioBuilder):
    """Multiplayer Gaming: Game lobby matchmaker, Redis leaderboards, UDP game server fleets."""

    def build(self) -> ScenarioContext:
        mult = self.get_scale_multiplier()
        acct = CloudAccount(
            account_id="acct-game-studio-11",
            name="Quantum Byte Game Studios",
            provider=CloudProvider.AWS,
            billing_account_id="ba-game-11",
            tags={"Domain": "Gaming"},
        )
        ctx = ScenarioContext(profile_name="Gaming", scale=self.scale, seed=self.seed, account=acct)

        vpc = SimulatedVPC(
            vpc_id="vpc-game-fleet",
            account_id=acct.account_id,
            region="us-west-2",
            name="game-servers-vpc",
            cidr_block="10.80.0.0/16",
        )
        ctx.vpcs.append(vpc)

        sub_fleet = SimulatedSubnet(
            subnet_id="sub-game-fleet-1",
            vpc_id=vpc.vpc_id,
            region="us-west-2",
            availability_zone="us-west-2a",
            cidr_block="10.80.1.0/24",
            tier="private",
        )
        ctx.subnets.append(sub_fleet)

        sg = SimulatedSecurityGroup(sg_id="sg-game", vpc_id=vpc.vpc_id, name="game-sg", description="Game Fleet SG")
        ctx.security_groups.append(sg)

        db_leaderboard = SimulatedDatabase(
            database_id="cache-game-leaderboard",
            name="game-redis-leaderboards",
            account_id=acct.account_id,
            region="us-west-2",
            vpc_id=vpc.vpc_id,
            subnet_ids=[sub_fleet.subnet_id],
            engine="redis",
            instance_class="cache.m6g.2xlarge",
            allocated_storage_gib=100,
            port=6379,
            endpoint="leaderboard.game.internal",
            monthly_cost_usd=760.0,
        )
        ctx.databases.append(db_leaderboard)

        # Game Server compute instances
        num_servers = 12 * mult
        fleet_ids = []
        for i in range(1, num_servers + 1):
            inst_id = f"ec2-game-server-{i:03d}"
            # Off-peak idle servers
            is_idle = (i > 8 * mult)
            inst = SimulatedCompute(
                instance_id=inst_id,
                name=f"game-fleet-box-{i}",
                account_id=acct.account_id,
                region="us-west-2",
                vpc_id=vpc.vpc_id,
                subnet_id=sub_fleet.subnet_id,
                security_group_ids=[sg.sg_id],
                instance_type="c6i.2xlarge",
                vcpu=8,
                memory_gib=16.0,
                monthly_cost_usd=250.0,
                hourly_rate_usd=0.34,
                private_ip=f"10.80.1.{10 + i}",
                app_id="app-game-match",
                service_id="svc-game-matchmaker",
            )
            ctx.compute.append(inst)
            fleet_ids.append(inst_id)
            ctx.telemetry[inst_id] = _create_telemetry(inst_id, is_idle=is_idle, is_hot=False, rng=self.rng)

            # Ground truth: Stopping idle off-peak servers is safe
            if is_idle:
                ctx.ground_truth.register_action(
                    GroundTruthAction(
                        action_id=f"gt-game-stop-idle-{i}",
                        target_id=inst_id,
                        action_type=ActionType.STOP,
                        is_safe=True,
                        reason="Zero player match activity in off-peak region. Stopping instance saves $250/mo.",
                        expected_savings_monthly_usd=250.0,
                        expected_risk="LOW",
                        expected_outcome="SUCCESS",
                    )
                )

        svc_game = SimulatedService(
            service_id="svc-game-matchmaker",
            app_id="app-game-match",
            name="Multiplayer Matchmaker Fleet",
            tier="worker",
            compute_ids=fleet_ids,
            database_ids=[db_leaderboard.database_id],
        )
        app_game = SimulatedApplication(
            app_id="app-game-match",
            name="Quantum Byte Arena Matchmaking",
            description="Real-time player lobbies and physics simulations",
            criticality=CriticalityLevel.TIER_1_MISSION_CRITICAL,
            owner_team="Game Ops",
            tech_lead="Kenji Takahashi",
            services=[svc_game],
        )
        ctx.applications.append(app_game)

        self.validate_consistency(ctx)
        return ctx


SCENARIO_PROFILES: Dict[str, Type[BaseScenarioBuilder]] = {
    "SaaS": SaaSScenarioBuilder,
    "Banking": BankingScenarioBuilder,
    "E-commerce": EcommerceScenarioBuilder,
    "AI Research": AIResearchScenarioBuilder,
    "Startup": StartupScenarioBuilder,
    "Healthcare": HealthcareScenarioBuilder,
    "Gaming": GamingScenarioBuilder,
}


def get_scenario_builder(profile_name: str, seed: int = 42, scale: SimulationScale = SimulationScale.SMALL) -> BaseScenarioBuilder:
    """Factory retrieving configured scenario builder by name."""
    norm = profile_name.strip()
    if norm.lower() in ("ai", "ai startup", "ai research"):
        norm = "AI Research"
    elif norm.lower() in ("retail", "e-commerce", "ecommerce"):
        norm = "E-commerce"
    elif norm.lower() in ("financial services", "banking", "finance"):
        norm = "Banking"

    builder_cls = SCENARIO_PROFILES.get(norm, SaaSScenarioBuilder)
    return builder_cls(seed=seed, scale=scale)
