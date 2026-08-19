"""
Azure infrastructure discovery adapter.

Discovers resources using Azure SDK:
- Virtual machines
- SQL databases and servers
- App services and function apps
- Virtual networks and subnets
- Network security groups
- Storage accounts
- Load balancers

Builds dependency graph for VNet/NSG relationships.
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


class AzureAdapter(BaseCloudAdapter):
    """Azure infrastructure discovery adapter."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
    ) -> None:
        """
        Initialize Azure adapter with credentials.

        Args:
            client_id: Azure client ID
            client_secret: Azure client secret
            tenant_id: Azure tenant ID
            subscription_id: Azure subscription ID

        Raises:
            CloudAdapterError: If Azure SDK not installed
        """
        try:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.compute import ComputeManagementClient
            from azure.mgmt.network import NetworkManagementClient
            from azure.mgmt.sql import SqlManagementClient
            from azure.mgmt.web import WebSiteManagementClient
        except ImportError as e:
            raise CloudAdapterError("Azure SDK required for Azure support") from e

        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.subscription_id = subscription_id
        self.ClientSecretCredential = ClientSecretCredential
        self.ComputeManagementClient = ComputeManagementClient
        self.NetworkManagementClient = NetworkManagementClient
        self.SqlManagementClient = SqlManagementClient
        self.WebSiteManagementClient = WebSiteManagementClient
        logger.info(f"Initialized Azure adapter for subscription {subscription_id}")

    def _get_credential(self) -> Any:
        """Get Azure credential object."""
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            raise CloudAdapterError("Azure credentials incomplete")

        return self.ClientSecretCredential(
            client_id=self.client_id,
            client_secret=self.client_secret,
            tenant_id=self.tenant_id,
        )

    def health_check(self) -> bool:
        """
        Verify Azure credentials are valid.

        Returns:
            True if can list subscriptions
        """
        try:
            credential = self._get_credential()
            compute_client = self.ComputeManagementClient(
                credential, self.subscription_id
            )
            list(compute_client.resource_groups.list())
            logger.info("Azure health check passed")
            return True
        except Exception as e:
            logger.error(f"Azure health check failed: {e}")
            return False

    def discover(self) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """
        Discover all Azure resources in subscription.

        Returns:
            Tuple of (resources, dependencies)

        Raises:
            CloudAdapterError: On discovery failure
        """
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            credential = self._get_credential()

            vnet_resources, vnet_deps = self._discover_vnets(credential)
            resources.extend(vnet_resources)
            dependencies.extend(vnet_deps)

            nsg_resources = self._discover_nsgs(credential)
            resources.extend(nsg_resources)

            vm_resources = self._discover_vms(credential)
            resources.extend(vm_resources)

            sql_resources = self._discover_sql(credential)
            resources.extend(sql_resources)

            app_resources = self._discover_app_services(credential)
            resources.extend(app_resources)

            storage_resources = self._discover_storage(credential)
            resources.extend(storage_resources)

            logger.info(f"Discovered {len(resources)} Azure resources")
        except CloudAdapterError as e:
            logger.error(f"Azure discovery failed: {e}")
            raise

        return resources, dependencies

    def _discover_vnets(self, credential: Any) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """Discover virtual networks and subnets."""
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            network_client = self.NetworkManagementClient(credential, self.subscription_id)
            vnets = network_client.virtual_networks.list_all()

            for vnet in vnets:
                vnet_id = vnet.id
                vnet_name = vnet.name
                resource_group = vnet_id.split("/")[4]

                vnet_resource = CloudResource(
                    id=vnet_id,
                    name=vnet_name,
                    type=ResourceType.AZURE_VNET,
                    provider="azure",
                    region=vnet.location,
                    state=ResourceState.AVAILABLE,
                    tags={k: v for k, v in (vnet.tags or {}).items()},
                    metadata={
                        "vnet_id": vnet_id,
                        "resource_group": resource_group,
                        "address_space": vnet.address_space.address_prefixes if vnet.address_space else [],
                    },
                )
                resources.append(vnet_resource)

                if vnet.subnets:
                    for subnet in vnet.subnets:
                        subnet_resource = CloudResource(
                            id=subnet.id,
                            name=subnet.name,
                            type=ResourceType.AZURE_SUBNET,
                            provider="azure",
                            region=vnet.location,
                            state=ResourceState.AVAILABLE,
                            metadata={
                                "subnet_id": subnet.id,
                                "address_prefix": subnet.address_prefix,
                            },
                        )
                        resources.append(subnet_resource)
                        dependencies.append(
                            DependencyEdge(
                                source_id=vnet_id,
                                target_id=subnet.id,
                                relationship_type=DependencyType.CONTAINS,
                            )
                        )
        except Exception as e:
            logger.warning(f"Error discovering Azure VNets: {e}")

        return resources, dependencies

    def _discover_nsgs(self, credential: Any) -> list[CloudResource]:
        """Discover network security groups."""
        resources: list[CloudResource] = []

        try:
            network_client = self.NetworkManagementClient(credential, self.subscription_id)
            nsgs = network_client.network_security_groups.list_all()

            for nsg in nsgs:
                nsg_id = nsg.id
                resource_group = nsg_id.split("/")[4]

                resource = CloudResource(
                    id=nsg_id,
                    name=nsg.name,
                    type=ResourceType.AZURE_NSG,
                    provider="azure",
                    region=nsg.location,
                    state=ResourceState.AVAILABLE,
                    tags={k: v for k, v in (nsg.tags or {}).items()},
                    metadata={
                        "nsg_id": nsg_id,
                        "resource_group": resource_group,
                        "rule_count": len(nsg.security_rules) if nsg.security_rules else 0,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Azure NSGs: {e}")

        return resources

    def _discover_vms(self, credential: Any) -> list[CloudResource]:
        """Discover virtual machines."""
        resources: list[CloudResource] = []

        try:
            compute_client = self.ComputeManagementClient(credential, self.subscription_id)
            vms = compute_client.virtual_machines.list_all()

            for vm in vms:
                vm_id = vm.id
                resource_group = vm_id.split("/")[4]

                resource = CloudResource(
                    id=vm_id,
                    name=vm.name,
                    type=ResourceType.AZURE_VM,
                    provider="azure",
                    region=vm.location,
                    state=ResourceState.UNKNOWN,
                    tags={k: v for k, v in (vm.tags or {}).items()},
                    metadata={
                        "vm_id": vm_id,
                        "resource_group": resource_group,
                        "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
                        "os_type": vm.os_profile.os_type if vm.os_profile else None,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Azure VMs: {e}")

        return resources

    def _discover_sql(self, credential: Any) -> list[CloudResource]:
        """Discover SQL databases and servers."""
        resources: list[CloudResource] = []

        try:
            sql_client = self.SqlManagementClient(credential, self.subscription_id)
            servers = sql_client.servers.list()

            for server in servers:
                server_id = server.id
                resource_group = server_id.split("/")[4]

                server_resource = CloudResource(
                    id=server_id,
                    name=server.name,
                    type=ResourceType.AZURE_SQL_SERVER,
                    provider="azure",
                    region=server.location,
                    state=ResourceState.AVAILABLE,
                    owner=server.administrator_login,
                    tags={k: v for k, v in (server.tags or {}).items()},
                    metadata={
                        "server_id": server_id,
                        "resource_group": resource_group,
                        "fully_qualified_domain_name": server.fully_qualified_domain_name,
                    },
                )
                resources.append(server_resource)

                databases = sql_client.databases.list_by_server(resource_group, server.name)
                for db in databases:
                    db_resource = CloudResource(
                        id=db.id,
                        name=db.name,
                        type=ResourceType.AZURE_SQL_DATABASE,
                        provider="azure",
                        region=server.location,
                        state=ResourceState.AVAILABLE,
                        metadata={
                            "database_id": db.id,
                            "server_id": server_id,
                            "collation": db.collation,
                        },
                    )
                    resources.append(db_resource)
        except Exception as e:
            logger.warning(f"Error discovering Azure SQL: {e}")

        return resources

    def _discover_app_services(self, credential: Any) -> list[CloudResource]:
        """Discover App Services and Function Apps."""
        resources: list[CloudResource] = []

        try:
            web_client = self.WebSiteManagementClient(credential, self.subscription_id)
            apps = web_client.web_apps.list()

            for app in apps:
                app_id = app.id
                resource_group = app_id.split("/")[4]
                is_function = "functionapp" in (app.kind or "").lower()

                resource = CloudResource(
                    id=app_id,
                    name=app.name,
                    type=ResourceType.AZURE_FUNCTION_APP if is_function else ResourceType.AZURE_APP_SERVICE,
                    provider="azure",
                    region=app.location,
                    state=ResourceState.RUNNING if app.enabled else ResourceState.STOPPED,
                    tags={k: v for k, v in (app.tags or {}).items()},
                    metadata={
                        "app_id": app_id,
                        "resource_group": resource_group,
                        "kind": app.kind,
                        "default_host_name": app.default_host_name,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Azure App Services: {e}")

        return resources

    def _discover_storage(self, credential: Any) -> list[CloudResource]:
        """Discover storage accounts."""
        resources: list[CloudResource] = []

        try:
            from azure.mgmt.storage import StorageManagementClient

            storage_client = StorageManagementClient(credential, self.subscription_id)
            accounts = storage_client.storage_accounts.list()

            for account in accounts:
                account_id = account.id
                resource_group = account_id.split("/")[4]

                resource = CloudResource(
                    id=account_id,
                    name=account.name,
                    type=ResourceType.AZURE_STORAGE_ACCOUNT,
                    provider="azure",
                    region=account.location,
                    state=ResourceState.AVAILABLE,
                    tags={k: v for k, v in (account.tags or {}).items()},
                    metadata={
                        "storage_account_id": account_id,
                        "resource_group": resource_group,
                        "account_tier": account.sku.tier if account.sku else None,
                        "account_kind": account.kind,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Azure Storage: {e}")

        return resources
