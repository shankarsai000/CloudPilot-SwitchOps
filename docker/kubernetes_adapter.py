"""
Kubernetes infrastructure discovery adapter.

Discovers cluster resources using Kubernetes Python client:
- Pods, Deployments, StatefulSets, DaemonSets
- Services, Ingresses
- ConfigMaps, Secrets
- PersistentVolumes, PersistentVolumeClaims
- Namespaces

Builds dependency graph (Deployment → Pods, Service → Pods, etc.).
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


class KubernetesAdapter(BaseCloudAdapter):
    """Kubernetes cluster discovery adapter."""

    def __init__(
        self,
        kubeconfig: Optional[str] = None,
        context: Optional[str] = None,
    ) -> None:
        """
        Initialize Kubernetes adapter.

        Args:
            kubeconfig: Path to kubeconfig file or YAML content
            context: Kubernetes context to use

        Raises:
            CloudAdapterError: If kubernetes client not installed
        """
        try:
            from kubernetes import client, config
        except ImportError as e:
            raise CloudAdapterError("kubernetes client required for K8s support") from e

        self.client = client
        self.config = config
        self.kubeconfig = kubeconfig
        self.context = context
        self.api_client = None
        self._init_client()
        logger.info("Initialized Kubernetes adapter")

    def _init_client(self) -> None:
        """Initialize Kubernetes API client."""
        try:
            if self.kubeconfig:
                self.config.load_kube_config(
                    config_file=self.kubeconfig,
                    context=self.context,
                )
            else:
                try:
                    self.config.load_incluster_config()
                except Exception:
                    self.config.load_kube_config(context=self.context)
            
            self.api_client = self.client.ApiClient()
            logger.info("Kubernetes API client initialized")
        except Exception as e:
            raise CloudAdapterError(f"Failed to initialize Kubernetes client: {e}") from e

    def health_check(self) -> bool:
        """
        Verify Kubernetes cluster connectivity.

        Returns:
            True if can list namespaces
        """
        try:
            v1 = self.client.CoreV1Api()
            v1.list_namespace()
            logger.info("Kubernetes health check passed")
            return True
        except Exception as e:
            logger.error(f"Kubernetes health check failed: {e}")
            return False

    def discover(self) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """
        Discover all Kubernetes resources in cluster.

        Returns:
            Tuple of (resources, dependencies)

        Raises:
            CloudAdapterError: On discovery failure
        """
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            namespaces = self._discover_namespaces()
            resources.extend(namespaces)

            for ns in namespaces:
                ns_name = ns.name
                
                pod_resources, pod_deps = self._discover_pods(ns_name)
                resources.extend(pod_resources)
                dependencies.extend(pod_deps)

                deploy_resources, deploy_deps = self._discover_deployments(ns_name)
                resources.extend(deploy_resources)
                dependencies.extend(deploy_deps)

                statefulset_resources = self._discover_statefulsets(ns_name)
                resources.extend(statefulset_resources)

                daemonset_resources = self._discover_daemonsets(ns_name)
                resources.extend(daemonset_resources)

                service_resources, service_deps = self._discover_services(ns_name)
                resources.extend(service_resources)
                dependencies.extend(service_deps)

                configmap_resources = self._discover_configmaps(ns_name)
                resources.extend(configmap_resources)

                secret_resources = self._discover_secrets(ns_name)
                resources.extend(secret_resources)

            pv_resources = self._discover_persistent_volumes()
            resources.extend(pv_resources)

            pvc_resources = self._discover_persistent_volume_claims()
            resources.extend(pvc_resources)

            logger.info(f"Discovered {len(resources)} Kubernetes resources")
        except CloudAdapterError as e:
            logger.error(f"Kubernetes discovery failed: {e}")
            raise

        return resources, dependencies

    def _discover_namespaces(self) -> list[CloudResource]:
        """Discover namespaces."""
        resources: list[CloudResource] = []

        try:
            v1 = self.client.CoreV1Api()
            namespaces = v1.list_namespace()

            for ns in namespaces.items:
                resource = CloudResource(
                    id=f"k8s-ns-{ns.metadata.name}",
                    name=ns.metadata.name,
                    type=ResourceType.K8S_NAMESPACE,
                    provider="k8s",
                    region="cluster",
                    state=ResourceState.AVAILABLE,
                    tags={k: v for k, v in (ns.metadata.labels or {}).items()},
                    metadata={
                        "namespace": ns.metadata.name,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Namespaces: {e}")

        return resources

    def _discover_pods(self, namespace: str) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """Discover pods and their relationships."""
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            v1 = self.client.CoreV1Api()
            pods = v1.list_namespaced_pod(namespace)

            for pod in pods.items:
                pod_id = f"k8s-pod-{namespace}-{pod.metadata.name}"

                state_map = {
                    "Pending": ResourceState.PENDING,
                    "Running": ResourceState.RUNNING,
                    "Succeeded": ResourceState.AVAILABLE,
                    "Failed": ResourceState.UNAVAILABLE,
                    "Unknown": ResourceState.UNKNOWN,
                }

                resource = CloudResource(
                    id=pod_id,
                    name=pod.metadata.name,
                    type=ResourceType.K8S_POD,
                    provider="k8s",
                    region="cluster",
                    state=state_map.get(pod.status.phase, ResourceState.UNKNOWN),
                    tags={k: v for k, v in (pod.metadata.labels or {}).items()},
                    metadata={
                        "namespace": namespace,
                        "pod_name": pod.metadata.name,
                        "containers": len(pod.spec.containers),
                        "owner_kind": pod.metadata.owner_references[0].kind if pod.metadata.owner_references else None,
                        "owner_name": pod.metadata.owner_references[0].name if pod.metadata.owner_references else None,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Pods in {namespace}: {e}")

        return resources, dependencies

    def _discover_deployments(self, namespace: str) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """Discover deployments."""
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            apps_v1 = self.client.AppsV1Api()
            deployments = apps_v1.list_namespaced_deployment(namespace)

            for deploy in deployments.items:
                deploy_id = f"k8s-deploy-{namespace}-{deploy.metadata.name}"

                resource = CloudResource(
                    id=deploy_id,
                    name=deploy.metadata.name,
                    type=ResourceType.K8S_DEPLOYMENT,
                    provider="k8s",
                    region="cluster",
                    state=ResourceState.AVAILABLE,
                    tags={k: v for k, v in (deploy.metadata.labels or {}).items()},
                    metadata={
                        "namespace": namespace,
                        "deployment_name": deploy.metadata.name,
                        "replicas": deploy.spec.replicas or 0,
                        "ready_replicas": deploy.status.ready_replicas or 0,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Deployments in {namespace}: {e}")

        return resources, dependencies

    def _discover_statefulsets(self, namespace: str) -> list[CloudResource]:
        """Discover StatefulSets."""
        resources: list[CloudResource] = []

        try:
            apps_v1 = self.client.AppsV1Api()
            statefulsets = apps_v1.list_namespaced_stateful_set(namespace)

            for sts in statefulsets.items:
                sts_id = f"k8s-sts-{namespace}-{sts.metadata.name}"

                resource = CloudResource(
                    id=sts_id,
                    name=sts.metadata.name,
                    type=ResourceType.K8S_STATEFULSET,
                    provider="k8s",
                    region="cluster",
                    state=ResourceState.AVAILABLE,
                    tags={k: v for k, v in (sts.metadata.labels or {}).items()},
                    metadata={
                        "namespace": namespace,
                        "statefulset_name": sts.metadata.name,
                        "replicas": sts.spec.replicas or 0,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering StatefulSets in {namespace}: {e}")

        return resources

    def _discover_daemonsets(self, namespace: str) -> list[CloudResource]:
        """Discover DaemonSets."""
        resources: list[CloudResource] = []

        try:
            apps_v1 = self.client.AppsV1Api()
            daemonsets = apps_v1.list_namespaced_daemon_set(namespace)

            for ds in daemonsets.items:
                ds_id = f"k8s-ds-{namespace}-{ds.metadata.name}"

                resource = CloudResource(
                    id=ds_id,
                    name=ds.metadata.name,
                    type=ResourceType.K8S_DAEMONSET,
                    provider="k8s",
                    region="cluster",
                    state=ResourceState.AVAILABLE,
                    tags={k: v for k, v in (ds.metadata.labels or {}).items()},
                    metadata={
                        "namespace": namespace,
                        "daemonset_name": ds.metadata.name,
                        "desired_number_scheduled": ds.status.desired_number_scheduled,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering DaemonSets in {namespace}: {e}")

        return resources

    def _discover_services(self, namespace: str) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """Discover services."""
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            v1 = self.client.CoreV1Api()
            services = v1.list_namespaced_service(namespace)

            for svc in services.items:
                svc_id = f"k8s-svc-{namespace}-{svc.metadata.name}"

                resource = CloudResource(
                    id=svc_id,
                    name=svc.metadata.name,
                    type=ResourceType.K8S_SERVICE,
                    provider="k8s",
                    region="cluster",
                    state=ResourceState.AVAILABLE,
                    tags={k: v for k, v in (svc.metadata.labels or {}).items()},
                    metadata={
                        "namespace": namespace,
                        "service_name": svc.metadata.name,
                        "service_type": svc.spec.type,
                        "cluster_ip": svc.spec.cluster_ip,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Services in {namespace}: {e}")

        return resources, dependencies

    def _discover_configmaps(self, namespace: str) -> list[CloudResource]:
        """Discover ConfigMaps."""
        resources: list[CloudResource] = []

        try:
            v1 = self.client.CoreV1Api()
            configmaps = v1.list_namespaced_config_map(namespace)

            for cm in configmaps.items:
                cm_id = f"k8s-cm-{namespace}-{cm.metadata.name}"

                resource = CloudResource(
                    id=cm_id,
                    name=cm.metadata.name,
                    type=ResourceType.K8S_CONFIGMAP,
                    provider="k8s",
                    region="cluster",
                    state=ResourceState.AVAILABLE,
                    metadata={
                        "namespace": namespace,
                        "configmap_name": cm.metadata.name,
                        "data_keys": list(cm.data.keys()) if cm.data else [],
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering ConfigMaps in {namespace}: {e}")

        return resources

    def _discover_secrets(self, namespace: str) -> list[CloudResource]:
        """Discover Secrets."""
        resources: list[CloudResource] = []

        try:
            v1 = self.client.CoreV1Api()
            secrets = v1.list_namespaced_secret(namespace)

            for secret in secrets.items:
                secret_id = f"k8s-secret-{namespace}-{secret.metadata.name}"

                resource = CloudResource(
                    id=secret_id,
                    name=secret.metadata.name,
                    type=ResourceType.K8S_SECRET,
                    provider="k8s",
                    region="cluster",
                    state=ResourceState.AVAILABLE,
                    metadata={
                        "namespace": namespace,
                        "secret_name": secret.metadata.name,
                        "secret_type": secret.type,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Secrets in {namespace}: {e}")

        return resources

    def _discover_persistent_volumes(self) -> list[CloudResource]:
        """Discover PersistentVolumes."""
        resources: list[CloudResource] = []

        try:
            v1 = self.client.CoreV1Api()
            pvs = v1.list_persistent_volume()

            for pv in pvs.items:
                pv_id = f"k8s-pv-{pv.metadata.name}"

                state_map = {
                    "Available": ResourceState.AVAILABLE,
                    "Bound": ResourceState.RUNNING,
                    "Released": ResourceState.STOPPED,
                    "Failed": ResourceState.UNAVAILABLE,
                }

                resource = CloudResource(
                    id=pv_id,
                    name=pv.metadata.name,
                    type=ResourceType.K8S_PERSISTENTVOLUME,
                    provider="k8s",
                    region="cluster",
                    state=state_map.get(pv.status.phase, ResourceState.UNKNOWN),
                    metadata={
                        "pv_name": pv.metadata.name,
                        "capacity": str(pv.spec.capacity.get("storage")) if pv.spec.capacity else None,
                        "storage_class": pv.spec.storage_class_name,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering PersistentVolumes: {e}")

        return resources

    def _discover_persistent_volume_claims(self) -> list[CloudResource]:
        """Discover PersistentVolumeClaims."""
        resources: list[CloudResource] = []

        try:
            v1 = self.client.CoreV1Api()
            pvcs = v1.list_persistent_volume_claim_for_all_namespaces()

            for pvc in pvcs.items:
                pvc_id = f"k8s-pvc-{pvc.metadata.namespace}-{pvc.metadata.name}"

                resource = CloudResource(
                    id=pvc_id,
                    name=pvc.metadata.name,
                    type=ResourceType.K8S_PERSISTENTVOLUMECLAIM,
                    provider="k8s",
                    region="cluster",
                    state=ResourceState.AVAILABLE if pvc.status.phase == "Bound" else ResourceState.PENDING,
                    metadata={
                        "namespace": pvc.metadata.namespace,
                        "pvc_name": pvc.metadata.name,
                        "capacity": str(pvc.spec.resources.requests.get("storage")) if pvc.spec.resources else None,
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering PersistentVolumeClaims: {e}")

        return resources
