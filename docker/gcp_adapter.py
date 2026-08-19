"""
GCP infrastructure discovery adapter.

Discovers resources using Google Cloud SDK:
- Compute instances and disks
- Cloud SQL databases
- Cloud Functions
- Cloud Run services
- Storage buckets
- VPCs and subnets
- Firewall rules

Builds dependency graph for VPC/Firewall relationships.
"""

import logging
from typing import Any, Optional

from aws_adapter import BaseCloudAdapter, CloudAdapterError
from models_resource import (
    CloudResource,
    DependencyEdge,
    DependencyType,
    ResourceState,
    ResourceType,
)

logger = logging.getLogger(__name__)


class GCPAdapter(BaseCloudAdapter):
    """GCP infrastructure discovery adapter."""

    def __init__(
        self,
        project_id: str,
        service_account_json: Optional[str] = None,
    ) -> None:
        """
        Initialize GCP adapter with credentials.

        Args:
            project_id: GCP project ID
            service_account_json: Service account JSON string or path

        Raises:
            CloudAdapterError: If GCP SDK not installed
        """
        try:
            from google.cloud import compute_v1, sql_v1, storage
            from google.cloud.functions_v1 import CloudFunctionsServiceClient
            from google.cloud import run_v2
        except ImportError as e:
            raise CloudAdapterError("Google Cloud SDK required for GCP support") from e

        self.project_id = project_id
        self.service_account_json = service_account_json
        self.compute_v1 = compute_v1
        self.sql_v1 = sql_v1
        self.storage = storage
        self.CloudFunctionsServiceClient = CloudFunctionsServiceClient
        self.run_v2 = run_v2
        logger.info(f"Initialized GCP adapter for project {project_id}")

    def health_check(self) -> bool:
        """
        Verify GCP credentials are valid.

        Returns:
            True if can list compute instances
        """
        try:
            client = self.compute_v1.InstancesClient()
            request = self.compute_v1.AggregatedListInstancesRequest(
                project=self.project_id
            )
            list(client.aggregated_list(request=request))
            logger.info("GCP health check passed")
            return True
        except Exception as e:
            logger.error(f"GCP health check failed: {e}")
            return False

    def discover(self) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """
        Discover all GCP resources in project.

        Returns:
            Tuple of (resources, dependencies)

        Raises:
            CloudAdapterError: On discovery failure
        """
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            vpc_resources, vpc_deps = self._discover_vpcs()
            resources.extend(vpc_resources)
            dependencies.extend(vpc_deps)

            firewall_resources = self._discover_firewalls()
            resources.extend(firewall_resources)

            compute_resources = self._discover_compute_instances()
            resources.extend(compute_resources)

            sql_resources = self._discover_cloud_sql()
            resources.extend(sql_resources)

            function_resources = self._discover_cloud_functions()
            resources.extend(function_resources)

            run_resources = self._discover_cloud_run()
            resources.extend(run_resources)

            storage_resources = self._discover_storage()
            resources.extend(storage_resources)

            logger.info(f"Discovered {len(resources)} GCP resources")
        except CloudAdapterError as e:
            logger.error(f"GCP discovery failed: {e}")
            raise

        return resources, dependencies

    def _discover_vpcs(self) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """Discover VPC networks and subnets."""
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            client = self.compute_v1.NetworksClient()
            request = self.compute_v1.ListNetworksRequest(project=self.project_id)
            networks = client.list(request=request)

            for network in networks:
                vpc_id = f"projects/{self.project_id}/global/networks/{network.name}"

                vpc_resource = CloudResource(
                    id=vpc_id,
                    name=network.name,
                    type=ResourceType.GCP_VPC,
                    provider="gcp",
                    region="global",
                    state=ResourceState.AVAILABLE,
                    metadata={
                        "vpc_id": vpc_id,
                        "auto_create_subnets": network.auto_create_subnetworks,
                        "ipv4_range": network.ipv4_range,
                    },
                )
                resources.append(vpc_resource)

                subnets = self._discover_subnets_for_vpc(network.name)
                for subnet in subnets:
                    resources.append(subnet)
                    dependencies.append(
                        DependencyEdge(
                            source_id=vpc_id,
                            target_id=subnet.id,
                            relationship_type=DependencyType.CONTAINS,
                        )
                    )
        except Exception as e:
            logger.warning(f"Error discovering GCP VPCs: {e}")

        return resources, dependencies

    def _discover_subnets_for_vpc(self, network_name: str) -> list[CloudResource]:
        """Discover subnets in a VPC."""
        resources: list[CloudResource] = []

        try:
            client = self.compute_v1.SubnetworksClient()
            request = self.compute_v1.AggregatedListSubnetworksRequest(
                project=self.project_id
            )

            for zone, response in client.aggregated_list(request=request).items():
                if response.subnetworks:
                    for subnet in response.subnetworks:
                        if network_name in subnet.network:
                            subnet_resource = CloudResource(
                                id=subnet.self_link,
                                name=subnet.name,
                                type=ResourceType.GCP_SUBNET,
                                provider="gcp",
                                region=subnet.region.split("/")[-1],
                                state=ResourceState.AVAILABLE,
                                metadata={
                                    "subnet_id": subnet.self_link,
                                    "ip_cidr_range": subnet.ip_cidr_range,
                                    "network": network_name,
                                },
                            )
                            resources.append(subnet_resource)
        except Exception as e:
            logger.warning(f"Error discovering GCP subnets for {network_name}: {e}")

        return resources

    def _discover_firewalls(self) -> list[CloudResource]:
        """Discover firewall rules."""
        resources: list[CloudResource] = []

        try:
            client = self.compute_v1.FirewallsClient()
            request = self.compute_v1.ListFirewallsRequest(project=self.project_id)
            firewalls = client.list(request=request)

            for fw in firewalls:
                fw_id = f"projects/{self.project_id}/global/firewalls/{fw.name}"

                resource = CloudResource(
                    id=fw_id,
                    name=fw.name,
                    type=ResourceType.GCP_FIREWALL_RULE,
                    provider="gcp",
                    region="global",
                    state=ResourceState.AVAILABLE if fw.enabled else ResourceState.UNAVAILABLE,
                    metadata={
                        "firewall_id": fw_id,
                        "network": fw.network,
                        "priority": fw.priority,
                        "direction": fw.direction,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering GCP Firewalls: {e}")

        return resources

    def _discover_compute_instances(self) -> list[CloudResource]:
        """Discover compute instances."""
        resources: list[CloudResource] = []

        try:
            client = self.compute_v1.InstancesClient()
            request = self.compute_v1.AggregatedListInstancesRequest(
                project=self.project_id
            )

            for zone, response in client.aggregated_list(request=request).items():
                if response.instances:
                    for instance in response.instances:
                        zone_name = zone.split("/")[-1]
                        instance_id = f"projects/{self.project_id}/zones/{zone_name}/instances/{instance.name}"

                        state_map = {
                            "RUNNING": ResourceState.RUNNING,
                            "TERMINATED": ResourceState.TERMINATED,
                            "STOPPING": ResourceState.STOPPED,
                            "PROVISIONING": ResourceState.PENDING,
                        }

                        resource = CloudResource(
                            id=instance_id,
                            name=instance.name,
                            type=ResourceType.GCP_COMPUTE_INSTANCE,
                            provider="gcp",
                            region=zone_name,
                            state=state_map.get(instance.status, ResourceState.UNKNOWN),
                            metadata={
                                "instance_id": instance_id,
                                "machine_type": instance.machine_type.split("/")[-1],
                                "zone": zone_name,
                            },
                        )
                        resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering GCP Compute Instances: {e}")

        return resources

    def _discover_cloud_sql(self) -> list[CloudResource]:
        """Discover Cloud SQL instances and databases."""
        resources: list[CloudResource] = []

        try:
            client = self.sql_v1.SqlInstancesServiceClient()
            request = self.sql_v1.SqlInstancesListRequest(project=self.project_id)
            instances = client.list(request=request)

            for instance in instances.items:
                instance_id = f"projects/{self.project_id}/instances/{instance.name}"

                state_map = {
                    "RUNNABLE": ResourceState.RUNNING,
                    "SUSPENDED": ResourceState.STOPPED,
                }

                resource = CloudResource(
                    id=instance_id,
                    name=instance.name,
                    type=ResourceType.GCP_SQL_INSTANCE,
                    provider="gcp",
                    region=instance.region,
                    state=state_map.get(instance.state, ResourceState.UNKNOWN),
                    metadata={
                        "instance_id": instance_id,
                        "database_version": instance.database_version,
                        "instance_type": instance.instance_type,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering GCP Cloud SQL: {e}")

        return resources

    def _discover_cloud_functions(self) -> list[CloudResource]:
        """Discover Cloud Functions."""
        resources: list[CloudResource] = []

        try:
            client = self.CloudFunctionsServiceClient()
            parent = f"projects/{self.project_id}/locations/-"
            functions = client.list_functions(request={"parent": parent})

            for func in functions:
                func_id = func.name

                resource = CloudResource(
                    id=func_id,
                    name=func.name.split("/")[-1],
                    type=ResourceType.GCP_CLOUD_FUNCTION,
                    provider="gcp",
                    region=func.name.split("/")[-3],
                    state=ResourceState.AVAILABLE,
                    metadata={
                        "function_id": func_id,
                        "runtime": getattr(func, "runtime", None),
                        "entry_point": getattr(func, "entry_point", None),
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering GCP Cloud Functions: {e}")

        return resources

    def _discover_cloud_run(self) -> list[CloudResource]:
        """Discover Cloud Run services."""
        resources: list[CloudResource] = []

        try:
            client = self.run_v2.ServicesClient()
            request = self.run_v2.ListServicesRequest(
                parent=f"projects/{self.project_id}/locations/-"
            )
            services = client.list_services(request=request)

            for service in services:
                service_id = service.name

                resource = CloudResource(
                    id=service_id,
                    name=service.name.split("/")[-1],
                    type=ResourceType.GCP_CLOUD_RUN_SERVICE,
                    provider="gcp",
                    region=service.name.split("/")[-3],
                    state=ResourceState.RUNNING if hasattr(service, "status") else ResourceState.AVAILABLE,
                    metadata={
                        "service_id": service_id,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering GCP Cloud Run: {e}")

        return resources

    def _discover_storage(self) -> list[CloudResource]:
        """Discover storage buckets."""
        resources: list[CloudResource] = []

        try:
            client = self.storage.Client(project=self.project_id)
            buckets = client.list_buckets()

            for bucket in buckets:
                bucket_id = f"projects/{self.project_id}/buckets/{bucket.name}"

                resource = CloudResource(
                    id=bucket_id,
                    name=bucket.name,
                    type=ResourceType.GCP_STORAGE_BUCKET,
                    provider="gcp",
                    region=bucket.location.lower(),
                    state=ResourceState.AVAILABLE,
                    metadata={
                        "bucket_id": bucket_id,
                        "location": bucket.location,
                        "storage_class": bucket.storage_class,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering GCP Storage: {e}")

        return resources
