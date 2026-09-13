"""
AWS infrastructure discovery adapter.

Discovers resources across AWS using boto3:
- EC2 instances, security groups, subnets, VPCs
- RDS databases and clusters
- Lambda functions
- S3 buckets
- Load balancers, VPC peering, NAT gateways
- IAM roles and policies

Builds dependency graph for VPC/SG relationships.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from models_resource import (
    CloudResource,
    DependencyEdge,
    DependencyType,
    ResourceState,
    ResourceType,
)

try:
    import boto3
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)


class CloudAdapterError(Exception):
    """Raised when cloud discovery fails."""

    pass


class BaseCloudAdapter(ABC):
    """Abstract base class for cloud adapters using Strategy pattern."""

    @abstractmethod
    def discover(self) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """
        Discover all resources in cloud account.

        Returns:
            Tuple of (resources, dependency_edges)

        Raises:
            CloudAdapterError: On discovery failure
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Verify cloud credentials and connectivity.

        Returns:
            True if credentials valid and accessible
        """
        pass


class AWSAdapter(BaseCloudAdapter):
    """AWS infrastructure discovery adapter."""

    def __init__(
        self,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        session_token: Optional[str] = None,
        regions: Optional[list[str]] = None,
    ) -> None:
        """
        Initialize AWS adapter with credentials.

        Args:
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            session_token: Optional session token for temp credentials
            regions: List of AWS regions to scan (default: all)

        Raises:
            CloudAdapterError: If boto3 not installed or init fails
        """
        if boto3 is None:
            raise CloudAdapterError("boto3 library required for AWS support")

        self.boto3 = boto3
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.session_token = session_token
        self.regions = regions or self._get_all_regions()
        self.ec2_client = None
        self.rds_client = None
        self.lambda_client = None
        self.s3_client = None
        self.elbv2_client = None
        logger.info(f"Initialized AWS adapter for regions: {self.regions}")

    def _get_all_regions(self) -> list[str]:
        """
        Get all available AWS regions.

        Returns:
            List of region names
        """
        try:
            ec2 = self.boto3.client("ec2")
            response = ec2.describe_regions()
            return [r["RegionName"] for r in response["Regions"]]
        except Exception as e:
            logger.warning(f"Could not fetch regions, using defaults: {e}")
            return ["us-east-1", "us-west-2", "eu-west-1"]

    def _get_ec2_client(self, region: str) -> Any:
        """Get or create EC2 client for region."""
        try:
            return self.boto3.client(
                "ec2",
                region_name=region,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                aws_session_token=self.session_token,
            )
        except Exception as e:
            raise CloudAdapterError(f"Failed to create EC2 client for {region}: {e}") from e

    def _get_rds_client(self, region: str) -> Any:
        """Get or create RDS client for region."""
        try:
            return self.boto3.client(
                "rds",
                region_name=region,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                aws_session_token=self.session_token,
            )
        except Exception as e:
            raise CloudAdapterError(f"Failed to create RDS client for {region}: {e}") from e

    def _get_lambda_client(self, region: str) -> Any:
        """Get or create Lambda client for region."""
        try:
            return self.boto3.client(
                "lambda",
                region_name=region,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                aws_session_token=self.session_token,
            )
        except Exception as e:
            raise CloudAdapterError(f"Failed to create Lambda client for {region}: {e}") from e

    def _get_s3_client(self) -> Any:
        """Get or create S3 client (global service)."""
        try:
            return self.boto3.client(
                "s3",
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                aws_session_token=self.session_token,
            )
        except Exception as e:
            raise CloudAdapterError(f"Failed to create S3 client: {e}") from e

    def health_check(self) -> bool:
        """
        Verify AWS credentials are valid.

        Returns:
            True if STS get_caller_identity succeeds

        Raises:
            CloudAdapterError: On credential verification failure
        """
        try:
            sts = self.boto3.client(
                "sts",
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                aws_session_token=self.session_token,
            )
            identity = sts.get_caller_identity()
            account_id = identity.get("Account")
            logger.info(f"AWS health check passed for account {account_id}")
            return True
        except Exception as e:
            logger.error(f"AWS health check failed: {e}")
            return False

    def discover(self) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """
        Discover all AWS resources across regions.

        Returns:
            Tuple of (resources, dependencies)

        Raises:
            CloudAdapterError: On discovery failure
        """
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        for region in self.regions:
            try:
                logger.info(f"Discovering AWS resources in {region}")
                region_resources, region_deps = self._discover_region(region)
                resources.extend(region_resources)
                dependencies.extend(region_deps)
            except CloudAdapterError as e:
                logger.error(f"Failed to discover region {region}: {e}")
                continue

        try:
            s3_resources = self._discover_s3()
            resources.extend(s3_resources)
        except CloudAdapterError as e:
            logger.error(f"Failed to discover S3: {e}")

        logger.info(f"Discovered {len(resources)} AWS resources")
        return resources, dependencies

    def _discover_region(self, region: str) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """Discover resources in single region."""
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        ec2 = self._get_ec2_client(region)
        rds = self._get_rds_client(region)
        lam = self._get_lambda_client(region)

        vpc_resources, vpc_deps = self._discover_vpcs(ec2, region)
        resources.extend(vpc_resources)
        dependencies.extend(vpc_deps)

        sg_resources, sg_deps = self._discover_security_groups(ec2, region)
        resources.extend(sg_resources)
        dependencies.extend(sg_deps)

        ec2_resources = self._discover_ec2_instances(ec2, region)
        resources.extend(ec2_resources)

        rds_resources = self._discover_rds(rds, region)
        resources.extend(rds_resources)

        lambda_resources = self._discover_lambda(lam, region)
        resources.extend(lambda_resources)

        return resources, dependencies

    def _discover_vpcs(self, ec2: Any, region: str) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """Discover VPCs and subnets."""
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            vpcs = ec2.describe_vpcs()["Vpcs"]
            for vpc in vpcs:
                vpc_id = vpc["VpcId"]
                resource = CloudResource(
                    id=vpc_id,
                    name=vpc.get("Tags", [{}])[0].get("Value", vpc_id),
                    type=ResourceType.VPC,
                    provider="aws",
                    region=region,
                    state=ResourceState.AVAILABLE,
                    tags={t["Key"]: t["Value"] for t in vpc.get("Tags", [])},
                    metadata={"vpc_id": vpc_id, "cidr_block": vpc["CidrBlock"]},
                )
                resources.append(resource)

                subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]
                for subnet in subnets:
                    subnet_id = subnet["SubnetId"]
                    subnet_resource = CloudResource(
                        id=subnet_id,
                        name=subnet.get("Tags", [{}])[0].get("Value", subnet_id),
                        type=ResourceType.SUBNET,
                        provider="aws",
                        region=region,
                        state=ResourceState.AVAILABLE,
                        tags={t["Key"]: t["Value"] for t in subnet.get("Tags", [])},
                        metadata={"subnet_id": subnet_id, "cidr_block": subnet["CidrBlockAssociationSet"][0]["CidrBlock"]},
                    )
                    resources.append(subnet_resource)
                    dependencies.append(
                        DependencyEdge(
                            source_id=vpc_id,
                            target_id=subnet_id,
                            relationship_type=DependencyType.CONTAINS,
                        )
                    )
        except Exception as e:
            logger.warning(f"Error discovering VPCs in {region}: {e}")

        return resources, dependencies

    def _discover_security_groups(self, ec2: Any, region: str) -> tuple[list[CloudResource], list[DependencyEdge]]:
        """Discover security groups."""
        resources: list[CloudResource] = []
        dependencies: list[DependencyEdge] = []

        try:
            sgs = ec2.describe_security_groups()["SecurityGroups"]
            for sg in sgs:
                sg_id = sg["GroupId"]
                resource = CloudResource(
                    id=sg_id,
                    name=sg.get("GroupName", sg_id),
                    type=ResourceType.SECURITY_GROUP,
                    provider="aws",
                    region=region,
                    state=ResourceState.AVAILABLE,
                    tags={t["Key"]: t["Value"] for t in sg.get("Tags", [])},
                    metadata={
                        "group_id": sg_id,
                        "vpc_id": sg.get("VpcId"),
                        "description": sg.get("GroupDescription"),
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering security groups in {region}: {e}")

        return resources, dependencies

    def _discover_ec2_instances(self, ec2: Any, region: str) -> list[CloudResource]:
        """Discover EC2 instances."""
        resources: list[CloudResource] = []

        try:
            instances = ec2.describe_instances()["Reservations"]
            for reservation in instances:
                for instance in reservation["Instances"]:
                    instance_id = instance["InstanceId"]
                    state_name = instance["State"]["Name"]

                    state_map = {
                        "running": ResourceState.RUNNING,
                        "stopped": ResourceState.STOPPED,
                        "terminated": ResourceState.TERMINATED,
                        "pending": ResourceState.PENDING,
                    }

                    resource = CloudResource(
                        id=instance_id,
                        name=next(
                            (t["Value"] for t in instance.get("Tags", []) if t["Key"] == "Name"),
                            instance_id,
                        ),
                        type=ResourceType.EC2_INSTANCE,
                        provider="aws",
                        region=region,
                        state=state_map.get(state_name, ResourceState.UNKNOWN),
                        tags={t["Key"]: t["Value"] for t in instance.get("Tags", [])},
                        metadata={
                            "instance_id": instance_id,
                            "instance_type": instance["InstanceType"],
                            "ami_id": instance["ImageId"],
                            "vpc_id": instance.get("VpcId"),
                        },
                    )
                    resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering EC2 instances in {region}: {e}")

        return resources

    def _discover_rds(self, rds: Any, region: str) -> list[CloudResource]:
        """Discover RDS instances and clusters."""
        resources: list[CloudResource] = []

        try:
            dbs = rds.describe_db_instances()["DBInstances"]
            for db in dbs:
                db_id = db["DBInstanceIdentifier"]
                resource = CloudResource(
                    id=db_id,
                    name=db_id,
                    type=ResourceType.RDS_DATABASE,
                    provider="aws",
                    region=region,
                    state=ResourceState.AVAILABLE if db["DBInstanceStatus"] == "available" else ResourceState.PENDING,
                    owner=db.get("MasterUsername"),
                    metadata={
                        "db_instance_identifier": db_id,
                        "engine": db["Engine"],
                        "instance_class": db["DBInstanceClass"],
                        "allocated_storage": db.get("AllocatedStorage"),
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering RDS in {region}: {e}")

        return resources

    def _discover_lambda(self, lam: Any, region: str) -> list[CloudResource]:
        """Discover Lambda functions."""
        resources: list[CloudResource] = []

        try:
            functions = lam.list_functions()["Functions"]
            for func in functions:
                func_name = func["FunctionName"]
                resource = CloudResource(
                    id=func["FunctionArn"],
                    name=func_name,
                    type=ResourceType.LAMBDA_FUNCTION,
                    provider="aws",
                    region=region,
                    state=ResourceState.AVAILABLE,
                    metadata={
                        "function_arn": func["FunctionArn"],
                        "runtime": func.get("Runtime"),
                        "handler": func.get("Handler"),
                        "memory_size": func.get("MemorySize"),
                        "timeout": func.get("Timeout"),
                    },
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering Lambda in {region}: {e}")

        return resources

    def _discover_s3(self) -> list[CloudResource]:
        """Discover S3 buckets (global service)."""
        resources: list[CloudResource] = []

        try:
            s3 = self._get_s3_client()
            buckets = s3.list_buckets()["Buckets"]
            for bucket in buckets:
                bucket_name = bucket["Name"]
                resource = CloudResource(
                    id=bucket_name,
                    name=bucket_name,
                    type=ResourceType.S3_BUCKET,
                    provider="aws",
                    region="us-east-1",
                    state=ResourceState.AVAILABLE,
                    metadata={"bucket_name": bucket_name},
                )
                resources.append(resource)
        except Exception as e:
            logger.warning(f"Error discovering S3 buckets: {e}")

        return resources
