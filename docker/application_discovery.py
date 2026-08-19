"""
Application Discovery Engine

Automatically discovers applications by analyzing cloud resources
from M1 using pluggable strategy patterns. Groups raw infrastructure
resources into logical application units.

Discovery strategies:
- Tag-based: Groups resources by 'app', 'application', 'service' tags
- Namespace: Groups K8s resources by namespace
- Naming convention: Groups resources by naming patterns
- Label: Groups by Helm/K8s labels (app.kubernetes.io/name)
"""

from __future__ import annotations

import logging
import re
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Optional

from models_application import (
    Application,
    ApplicationType,
    EnvironmentType,
    ServiceTier,
)
from models_resource import CloudResource, ResourceType

logger = logging.getLogger(__name__)


class DiscoveryStrategy(ABC):
    """Abstract base class for application discovery strategies."""

    @abstractmethod
    def discover(
        self, resources: list[CloudResource]
    ) -> dict[str, list[CloudResource]]:
        """Discover application groups from resources.

        Args:
            resources: List of M1 cloud resources

        Returns:
            Dict mapping application name to its resources
        """
        ...

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Human-readable strategy name for audit trail."""
        ...


class TagBasedStrategy(DiscoveryStrategy):
    """Groups resources by common application tags.

    Scans resource tags for keys like 'app', 'application', 'service',
    'microservice', 'project' and groups resources sharing the same value.
    """

    TAG_KEYS: list[str] = [
        "app",
        "application",
        "service",
        "microservice",
        "project",
        "stack",
        "component",
        "App",
        "Application",
        "Service",
    ]

    @property
    def strategy_name(self) -> str:
        """Return strategy identifier."""
        return "tag_based"

    def discover(
        self, resources: list[CloudResource]
    ) -> dict[str, list[CloudResource]]:
        """Group resources by application tag values.

        Args:
            resources: List of M1 cloud resources

        Returns:
            Dict mapping application name → resources
        """
        groups: dict[str, list[CloudResource]] = defaultdict(list)

        for resource in resources:
            app_name = self._extract_app_tag(resource.tags)
            if app_name:
                normalized = self._normalize_name(app_name)
                groups[normalized].append(resource)

        logger.info(
            "TagBasedStrategy discovered %d application groups", len(groups)
        )
        return dict(groups)

    def _extract_app_tag(self, tags: dict[str, str]) -> Optional[str]:
        """Extract application name from resource tags.

        Args:
            tags: Resource tag dictionary

        Returns:
            Application name or None
        """
        for key in self.TAG_KEYS:
            if key in tags and tags[key].strip():
                return tags[key].strip()
        return None

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize application name to lowercase-kebab-case.

        Args:
            name: Raw application name

        Returns:
            Normalized name
        """
        normalized = name.lower().strip()
        normalized = re.sub(r"[_\s]+", "-", normalized)
        normalized = re.sub(r"[^a-z0-9\-]", "", normalized)
        normalized = re.sub(r"-+", "-", normalized).strip("-")
        return normalized or "unknown"


class NamespaceStrategy(DiscoveryStrategy):
    """Groups Kubernetes resources by namespace.

    All resources within a K8s namespace are assumed to belong
    to the same logical application.
    """

    SYSTEM_NAMESPACES: set[str] = {
        "kube-system",
        "kube-public",
        "kube-node-lease",
        "default",
        "ingress-nginx",
        "cert-manager",
        "monitoring",
        "istio-system",
        "linkerd",
    }

    @property
    def strategy_name(self) -> str:
        """Return strategy identifier."""
        return "namespace"

    def discover(
        self, resources: list[CloudResource]
    ) -> dict[str, list[CloudResource]]:
        """Group K8s resources by namespace.

        Args:
            resources: List of M1 cloud resources

        Returns:
            Dict mapping namespace/application name → resources
        """
        groups: dict[str, list[CloudResource]] = defaultdict(list)

        k8s_types = {
            ResourceType.K8S_POD,
            ResourceType.K8S_DEPLOYMENT,
            ResourceType.K8S_STATEFULSET,
            ResourceType.K8S_DAEMONSET,
            ResourceType.K8S_SERVICE,
            ResourceType.K8S_INGRESS,
            ResourceType.K8S_CONFIGMAP,
            ResourceType.K8S_SECRET,
            ResourceType.K8S_JOB,
            ResourceType.K8S_CRONJOB,
        }

        for resource in resources:
            if resource.type not in k8s_types:
                continue

            namespace = resource.metadata.get("namespace", "")
            if not namespace or namespace in self.SYSTEM_NAMESPACES:
                continue

            groups[namespace].append(resource)

        logger.info(
            "NamespaceStrategy discovered %d application groups", len(groups)
        )
        return dict(groups)


class NamingConventionStrategy(DiscoveryStrategy):
    """Groups resources by shared naming prefix patterns.

    Extracts application name from resource names using common
    naming patterns like 'payment-api-*', 'order-service-*'.
    """

    @property
    def strategy_name(self) -> str:
        """Return strategy identifier."""
        return "naming_convention"

    def discover(
        self, resources: list[CloudResource]
    ) -> dict[str, list[CloudResource]]:
        """Group resources by naming prefix.

        Args:
            resources: List of M1 cloud resources

        Returns:
            Dict mapping application name → resources
        """
        groups: dict[str, list[CloudResource]] = defaultdict(list)

        for resource in resources:
            app_prefix = self._extract_prefix(resource.name)
            if app_prefix and len(app_prefix) >= 3:
                groups[app_prefix].append(resource)

        # Filter out groups with only 1 resource (likely false positives)
        filtered = {
            name: resources
            for name, resources in groups.items()
            if len(resources) >= 2
        }

        logger.info(
            "NamingConventionStrategy discovered %d application groups",
            len(filtered),
        )
        return filtered

    @staticmethod
    def _extract_prefix(name: str) -> Optional[str]:
        """Extract application prefix from resource name.

        Handles patterns like:
        - payment-api-prod-001 → payment-api
        - order_service_v2 → order-service
        - web-frontend → web-frontend

        Args:
            name: Resource name

        Returns:
            Extracted prefix or None
        """
        if not name:
            return None

        normalized = name.lower().replace("_", "-")

        # Remove common suffixes: env names, version numbers, instance IDs
        suffix_patterns = [
            r"-(?:prod|staging|dev|test|qa|uat|sandbox)(?:-\d+)?$",
            r"-(?:v\d+|[a-f0-9]{8})$",
            r"-\d{3,}$",
            r"-(?:primary|secondary|replica|master|slave)$",
            r"-(?:blue|green|canary)$",
        ]

        cleaned = normalized
        for pattern in suffix_patterns:
            cleaned = re.sub(pattern, "", cleaned)

        return cleaned if cleaned and cleaned != normalized else normalized.rsplit("-", 1)[0] if "-" in normalized else None


class LabelStrategy(DiscoveryStrategy):
    """Groups resources by Kubernetes/Helm labels.

    Uses standard K8s labels like 'app.kubernetes.io/name',
    'helm.sh/chart', 'app.kubernetes.io/part-of'.
    """

    LABEL_KEYS: list[str] = [
        "app.kubernetes.io/name",
        "app.kubernetes.io/part-of",
        "app.kubernetes.io/instance",
        "helm.sh/chart",
        "argocd.argoproj.io/application",
    ]

    @property
    def strategy_name(self) -> str:
        """Return strategy identifier."""
        return "label"

    def discover(
        self, resources: list[CloudResource]
    ) -> dict[str, list[CloudResource]]:
        """Group resources by K8s/Helm labels.

        Args:
            resources: List of M1 cloud resources

        Returns:
            Dict mapping application name → resources
        """
        groups: dict[str, list[CloudResource]] = defaultdict(list)

        for resource in resources:
            labels = resource.metadata.get("labels", {})
            if not isinstance(labels, dict):
                continue

            app_name = self._extract_label(labels)
            if app_name:
                groups[app_name.lower()].append(resource)

        logger.info(
            "LabelStrategy discovered %d application groups", len(groups)
        )
        return dict(groups)

    def _extract_label(self, labels: dict[str, str]) -> Optional[str]:
        """Extract application name from labels.

        Args:
            labels: Label dictionary

        Returns:
            Application name or None
        """
        for key in self.LABEL_KEYS:
            if key in labels and labels[key].strip():
                return labels[key].strip()
        return None


class ApplicationDiscoveryEngine:
    """Main application discovery engine using pluggable strategies.

    Runs multiple discovery strategies against M1 resources,
    merges and deduplicates results to produce a unified
    application inventory.
    """

    def __init__(
        self,
        strategies: Optional[list[DiscoveryStrategy]] = None,
    ) -> None:
        """Initialize discovery engine with strategies.

        Args:
            strategies: List of strategies to use (defaults to all built-in)
        """
        self.strategies: list[DiscoveryStrategy] = strategies or [
            TagBasedStrategy(),
            NamespaceStrategy(),
            NamingConventionStrategy(),
            LabelStrategy(),
        ]
        logger.info(
            "ApplicationDiscoveryEngine initialized with %d strategies: %s",
            len(self.strategies),
            [s.strategy_name for s in self.strategies],
        )

    def discover(self, resources: list[CloudResource]) -> list[Application]:
        """Run all strategies and merge results into Application objects.

        Args:
            resources: List of M1 cloud resources

        Returns:
            List of discovered Application objects
        """
        if not resources:
            logger.warning("No resources provided for application discovery")
            return []

        # Collect groups from all strategies
        all_groups: dict[str, dict[str, list[CloudResource]]] = {}
        for strategy in self.strategies:
            try:
                groups = strategy.discover(resources)
                for app_name, app_resources in groups.items():
                    if app_name not in all_groups:
                        all_groups[app_name] = {
                            "resources": [],
                            "source": strategy.strategy_name,
                        }
                    all_groups[app_name]["resources"].extend(app_resources)
            except Exception as e:
                logger.error(
                    "Strategy %s failed: %s", strategy.strategy_name, e
                )

        # Deduplicate resources within each group
        merged = self._merge_groups(all_groups)

        # Convert to Application objects
        applications = [
            self._create_application(name, data)
            for name, data in merged.items()
        ]

        logger.info(
            "Application discovery complete: %d applications from %d resources",
            len(applications),
            len(resources),
        )
        return applications

    def _merge_groups(
        self, groups: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Deduplicate resources within each application group.

        Args:
            groups: Raw groups from strategies

        Returns:
            Merged groups with deduplicated resources
        """
        merged: dict[str, dict[str, Any]] = {}

        for app_name, data in groups.items():
            seen_ids: set[str] = set()
            unique_resources: list[CloudResource] = []

            resource_list = data["resources"] if isinstance(data.get("resources"), list) else data.get("resources", [])
            for resource in resource_list:
                if resource.id not in seen_ids:
                    seen_ids.add(resource.id)
                    unique_resources.append(resource)

            merged[app_name] = {
                "resources": unique_resources,
                "source": data.get("source", "unknown"),
            }

        return merged

    def _create_application(
        self, name: str, data: dict[str, Any]
    ) -> Application:
        """Create an Application model from discovered resource group.

        Args:
            name: Application name
            data: Discovery data with resources and source

        Returns:
            Application model instance
        """
        resources: list[CloudResource] = data.get("resources", [])
        source: str = data.get("source", "unknown")

        app_type = self._infer_application_type(resources)
        environment = self._infer_environment(resources)
        tier = self._infer_tier(resources)

        # Collect all tags from resources
        merged_tags: dict[str, str] = {}
        for resource in resources:
            merged_tags.update(resource.tags)

        return Application(
            application_id=f"app-{name}-{uuid.uuid4().hex[:8]}",
            name=self._humanize_name(name),
            application_type=app_type,
            environment=environment,
            tier=tier,
            resource_ids=[r.id for r in resources],
            tags=merged_tags,
            discovery_source=source,
            metadata={
                "resource_count": len(resources),
                "resource_types": list(
                    {r.type.value for r in resources}
                ),
                "providers": list({r.provider for r in resources}),
            },
        )

    @staticmethod
    def _infer_application_type(
        resources: list[CloudResource],
    ) -> ApplicationType:
        """Infer application type from resource composition.

        Args:
            resources: Application's resources

        Returns:
            Inferred ApplicationType
        """
        types = {r.type for r in resources}

        lambda_types = {ResourceType.LAMBDA_FUNCTION, ResourceType.GCP_CLOUD_FUNCTION, ResourceType.AZURE_FUNCTION_APP}
        if types & lambda_types and not (types & {ResourceType.EC2_INSTANCE, ResourceType.AZURE_VM, ResourceType.GCP_COMPUTE_INSTANCE}):
            return ApplicationType.SERVERLESS

        k8s_types = {ResourceType.K8S_DEPLOYMENT, ResourceType.K8S_STATEFULSET, ResourceType.K8S_POD}
        if types & k8s_types:
            return ApplicationType.MICROSERVICE

        container_types = {ResourceType.ECS_SERVICE, ResourceType.GCP_CLOUD_RUN_SERVICE}
        if types & container_types:
            return ApplicationType.MICROSERVICE

        compute_types = {ResourceType.EC2_INSTANCE, ResourceType.AZURE_VM, ResourceType.GCP_COMPUTE_INSTANCE}
        if types & compute_types:
            # Check if it has multiple services (microservice) or just one (monolith)
            compute_count = sum(1 for r in resources if r.type in compute_types)
            if compute_count >= 3:
                return ApplicationType.MICROSERVICE
            return ApplicationType.MONOLITH

        storage_types = {ResourceType.S3_BUCKET, ResourceType.AZURE_STORAGE_ACCOUNT, ResourceType.GCP_STORAGE_BUCKET}
        cdn_types = {ResourceType.CLOUDFRONT_DISTRIBUTION}
        if (types & storage_types or types & cdn_types) and not types & compute_types:
            return ApplicationType.STATIC_SITE

        return ApplicationType.UNKNOWN

    @staticmethod
    def _infer_environment(
        resources: list[CloudResource],
    ) -> EnvironmentType:
        """Infer deployment environment from resource tags and names.

        Args:
            resources: Application's resources

        Returns:
            Inferred EnvironmentType
        """
        env_indicators: dict[EnvironmentType, list[str]] = {
            EnvironmentType.PRODUCTION: ["prod", "production", "prd", "live"],
            EnvironmentType.STAGING: ["staging", "stg", "stage", "preprod", "pre-prod"],
            EnvironmentType.DEVELOPMENT: ["dev", "development", "develop"],
            EnvironmentType.TESTING: ["test", "testing", "tst", "qa", "uat"],
            EnvironmentType.SANDBOX: ["sandbox", "sbx", "experiment"],
        }

        for resource in resources:
            # Check tags
            for tag_key in ["env", "environment", "Environment", "Env", "stage"]:
                tag_value = resource.tags.get(tag_key, "").lower()
                for env_type, indicators in env_indicators.items():
                    if tag_value in indicators:
                        return env_type

            # Check resource name
            name_lower = resource.name.lower()
            for env_type, indicators in env_indicators.items():
                for indicator in indicators:
                    if indicator in name_lower:
                        return env_type

        return EnvironmentType.UNKNOWN

    @staticmethod
    def _infer_tier(resources: list[CloudResource]) -> ServiceTier:
        """Infer service tier from resource composition and tags.

        Args:
            resources: Application's resources

        Returns:
            Inferred ServiceTier
        """
        for resource in resources:
            tier_value = resource.tags.get("tier", "").lower()
            if tier_value in ("1", "tier-1", "tier_1", "critical"):
                return ServiceTier.TIER_1
            if tier_value in ("2", "tier-2", "tier_2", "important"):
                return ServiceTier.TIER_2
            if tier_value in ("3", "tier-3", "tier_3", "standard"):
                return ServiceTier.TIER_3
            if tier_value in ("4", "tier-4", "tier_4", "experimental"):
                return ServiceTier.TIER_4

        # Heuristic: applications with ALB/NLB + database are likely higher tier
        types = {r.type for r in resources}
        has_lb = bool(types & {ResourceType.ALB, ResourceType.NLB, ResourceType.ELB, ResourceType.AZURE_LOAD_BALANCER, ResourceType.GCP_LOAD_BALANCER})
        has_db = bool(types & {ResourceType.RDS_DATABASE, ResourceType.RDS_CLUSTER, ResourceType.AZURE_SQL_DATABASE, ResourceType.GCP_SQL_INSTANCE, ResourceType.DYNAMODB_TABLE})

        if has_lb and has_db:
            return ServiceTier.TIER_2
        if has_lb or has_db:
            return ServiceTier.TIER_3

        return ServiceTier.UNKNOWN

    @staticmethod
    def _humanize_name(name: str) -> str:
        """Convert kebab-case name to human-readable title.

        Args:
            name: kebab-case application name

        Returns:
            Title-cased name (e.g. 'payment-api' → 'Payment Api')
        """
        return name.replace("-", " ").replace("_", " ").title()
