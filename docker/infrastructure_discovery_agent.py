"""
Infrastructure Discovery Agent orchestrator.

Main entry point for discovering cloud resources across AWS, Azure, GCP, Kubernetes.
Uses ThreadPoolExecutor to parallelize discovery across cloud providers.
Deduplicates resources, builds dependency graph, saves to PostgreSQL repository.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from aws_adapter import AWSAdapter, CloudAdapterError
from azure_adapter import AzureAdapter
from config_credentials import CredentialManager
from gcp_adapter import GCPAdapter
from kubernetes_adapter import KubernetesAdapter
from models_resource import CloudResource, DependencyEdge, ResourceGraph

logger = logging.getLogger(__name__)


class CloudAdapterFactory:
    """Factory for creating cloud adapter instances using Adapter pattern."""

    @staticmethod
    def create_aws_adapter(cred_manager: CredentialManager) -> Optional[AWSAdapter]:
        """
        Create AWS adapter if credentials available.

        Args:
            cred_manager: Credential manager instance

        Returns:
            AWSAdapter instance or None if credentials missing
        """
        access_key, secret_key, session_token = cred_manager.get_aws_credentials()
        if not access_key or not secret_key:
            logger.info("AWS credentials not available, skipping AWS adapter")
            return None

        try:
            return AWSAdapter(
                access_key_id=access_key,
                secret_access_key=secret_key,
                session_token=session_token,
            )
        except CloudAdapterError as e:
            logger.error(f"Failed to create AWS adapter: {e}")
            return None

    @staticmethod
    def create_azure_adapter(cred_manager: CredentialManager) -> Optional[AzureAdapter]:
        """
        Create Azure adapter if credentials available.

        Args:
            cred_manager: Credential manager instance

        Returns:
            AzureAdapter instance or None if credentials missing
        """
        client_id, client_secret, tenant_id, subscription_id = cred_manager.get_azure_credentials()
        if not all([client_id, client_secret, tenant_id, subscription_id]):
            logger.info("Azure credentials not complete, skipping Azure adapter")
            return None

        try:
            return AzureAdapter(
                client_id=client_id,
                client_secret=client_secret,
                tenant_id=tenant_id,
                subscription_id=subscription_id,
            )
        except CloudAdapterError as e:
            logger.error(f"Failed to create Azure adapter: {e}")
            return None

    @staticmethod
    def create_gcp_adapter(cred_manager: CredentialManager) -> Optional[GCPAdapter]:
        """
        Create GCP adapter if credentials available.

        Args:
            cred_manager: Credential manager instance

        Returns:
            GCPAdapter instance or None if credentials missing
        """
        project_id = cred_manager.get("GCP_PROJECT_ID")
        service_account_json = cred_manager.get_gcp_credentials()

        if not project_id:
            logger.info("GCP project ID not available, skipping GCP adapter")
            return None

        try:
            return GCPAdapter(
                project_id=project_id,
                service_account_json=service_account_json,
            )
        except CloudAdapterError as e:
            logger.error(f"Failed to create GCP adapter: {e}")
            return None

    @staticmethod
    def create_k8s_adapter(cred_manager: CredentialManager) -> Optional[KubernetesAdapter]:
        """
        Create Kubernetes adapter if credentials available.

        Args:
            cred_manager: Credential manager instance

        Returns:
            KubernetesAdapter instance or None if credentials missing
        """
        kubeconfig = cred_manager.get_k8s_kubeconfig()

        try:
            return KubernetesAdapter(kubeconfig=kubeconfig)
        except CloudAdapterError as e:
            logger.warning(f"Failed to create Kubernetes adapter: {e}")
            return None


class DiscoveryAgent:
    """
    Infrastructure discovery orchestrator.

    Manages discovery workflow across multiple cloud providers.
    Handles parallel discovery, deduplication, and dependency tracking.
    """

    def __init__(
        self,
        credential_manager: Optional[CredentialManager] = None,
        max_workers: int = 4,
    ) -> None:
        """
        Initialize discovery agent.

        Args:
            credential_manager: Optional credential manager (auto-creates if None)
            max_workers: Max parallel discovery threads
        """
        self.cred_manager = credential_manager or CredentialManager()
        self.max_workers = max_workers
        self.adapters: dict[str, object] = {}
        self.resource_cache: dict[str, CloudResource] = {}
        self.dependency_cache: list[DependencyEdge] = []
        logger.info(f"Initialized DiscoveryAgent with {max_workers} workers")

    def _load_adapters(self) -> None:
        """Load available cloud adapters."""
        self.adapters.clear()

        aws = CloudAdapterFactory.create_aws_adapter(self.cred_manager)
        if aws:
            self.adapters["aws"] = aws

        azure = CloudAdapterFactory.create_azure_adapter(self.cred_manager)
        if azure:
            self.adapters["azure"] = azure

        gcp = CloudAdapterFactory.create_gcp_adapter(self.cred_manager)
        if gcp:
            self.adapters["gcp"] = gcp

        k8s = CloudAdapterFactory.create_k8s_adapter(self.cred_manager)
        if k8s:
            self.adapters["k8s"] = k8s

        logger.info(f"Loaded {len(self.adapters)} cloud adapters: {list(self.adapters.keys())}")

    def discover(self) -> ResourceGraph:
        """
        Execute discovery across all available cloud providers.

        Runs adapters in parallel using ThreadPoolExecutor.
        Deduplicates resources by (provider, region, resource_id).
        Returns unified ResourceGraph with all resources and dependencies.

        Returns:
            ResourceGraph containing discovered resources, dependencies, statistics

        Raises:
            No exceptions - logs failures and returns partial results if adapters fail
        """
        logger.info("Starting infrastructure discovery")
        self._load_adapters()

        if not self.adapters:
            logger.error("No cloud adapters available - check credentials")
            return ResourceGraph(failures=["No cloud adapters configured"])

        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []
        failures: list[str] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for provider_name, adapter in self.adapters.items():
                future = executor.submit(self._discover_provider, provider_name, adapter)
                futures[future] = provider_name

            for future in as_completed(futures):
                provider_name = futures[future]
                try:
                    prov_resources, prov_deps = future.result()
                    resources.extend(prov_resources)
                    dependencies.extend(prov_deps)
                    logger.info(
                        f"{provider_name}: discovered {len(prov_resources)} resources"
                    )
                except Exception as e:
                    error_msg = f"{provider_name} discovery failed: {e}"
                    logger.error(error_msg)
                    failures.append(error_msg)

        resources = self._deduplicate_resources(resources)
        graph = self._build_graph(resources, dependencies, failures)

        logger.info(
            f"Discovery complete: {len(resources)} resources, "
            f"{len(dependencies)} dependencies, {len(failures)} failures"
        )
        return graph

    def _discover_provider(self, provider_name: str, adapter: object) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """
        Discover resources from single cloud provider.

        Args:
            provider_name: Provider identifier (aws, azure, gcp, k8s)
            adapter: Cloud adapter instance

        Returns:
            Tuple of (resources, dependencies)

        Raises:
            Exception on discovery failure
        """
        try:
            logger.debug(f"Starting {provider_name} discovery")
            resources, dependencies = adapter.discover()
            logger.debug(f"{provider_name}: got {len(resources)} resources")
            return resources, dependencies
        except CloudAdapterError as e:
            logger.error(f"{provider_name} adapter error: {e}")
            raise

    def _deduplicate_resources(self, resources: list[CloudResource]) -> list[CloudResource]:
        """
        Deduplicate resources by (provider, region, resource_id).

        Later resources override earlier ones (newer discoveries win).

        Args:
            resources: List of discovered resources

        Returns:
            Deduplicated resources list
        """
        seen: dict[tuple[str, Optional[str], str], CloudResource] = {}

        for resource in resources:
            key = (resource.provider, resource.region, resource.id)
            seen[key] = resource

        logger.debug(f"Deduplicated {len(resources)} resources to {len(seen)}")
        return list(seen.values())

    def _build_graph(
        self,
        resources: list[CloudResource],
        dependencies: list[DependencyEdge],
        failures: list[str],
    ) -> ResourceGraph:
        """
        Build ResourceGraph with statistics.

        Args:
            resources: Discovered resources
            dependencies: Resource dependencies
            failures: List of discovery failures

        Returns:
            Complete ResourceGraph
        """
        resources_by_type: dict[str, int] = {}
        resources_by_provider: dict[str, int] = {}

        for resource in resources:
            resources_by_type[resource.type.value] = resources_by_type.get(resource.type.value, 0) + 1
            resources_by_provider[resource.provider] = resources_by_provider.get(resource.provider, 0) + 1

        return ResourceGraph(
            resources=resources,
            dependencies=dependencies,
            total_resources=len(resources),
            resources_by_type=resources_by_type,
            resources_by_provider=resources_by_provider,
            failures=failures,
        )


def main() -> None:
    """Entry point for running discovery agent as service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    agent = DiscoveryAgent()
    graph = agent.discover()

    logger.info(f"=== Discovery Complete ===")
    logger.info(f"Total Resources: {graph.total_resources}")
    logger.info(f"Resources by Type: {graph.resources_by_type}")
    logger.info(f"Resources by Provider: {graph.resources_by_provider}")
    logger.info(f"Dependencies: {len(graph.dependencies)}")
    logger.info(f"Failures: {len(graph.failures)}")

    for failure in graph.failures:
        logger.warning(f"  - {failure}")


if __name__ == "__main__":
    main()
