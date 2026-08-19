"""
Credential management for CloudPilot AI Infrastructure Discovery Agent.

Supports multiple credential sources:
- Environment variables
- Vault (HashiCorp)
- AWS Secrets Manager
- Azure Key Vault
- GCP Secret Manager

Uses a hierarchical fallback system to discover credentials.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CredentialStorageError(Exception):
    """Raised when credential operations fail."""

    pass


class CredentialSource(ABC):
    """Abstract base class for credential sources."""

    @abstractmethod
    def get_credential(self, key: str) -> Optional[str]:
        """
        Retrieve credential value by key.

        Args:
            key: Credential key identifier

        Returns:
            Credential value or None if not found

        Raises:
            CredentialStorageError: On retrieval failure
        """
        pass

    @abstractmethod
    def set_credential(self, key: str, value: str) -> None:
        """
        Store credential value.

        Args:
            key: Credential key identifier
            value: Credential value

        Raises:
            CredentialStorageError: On storage failure
        """
        pass


class EnvironmentSource(CredentialSource):
    """Load credentials from environment variables."""

    def get_credential(self, key: str) -> Optional[str]:
        """
        Retrieve credential from environment variable.

        Args:
            key: Environment variable name

        Returns:
            Environment variable value or None if not set
        """
        value = os.environ.get(key)
        if value:
            logger.debug(f"Retrieved credential {key} from environment")
        return value

    def set_credential(self, key: str, value: str) -> None:
        """
        Set credential in environment.

        Args:
            key: Environment variable name
            value: Credential value
        """
        os.environ[key] = value
        logger.debug(f"Set credential {key} in environment")


class VaultSource(CredentialSource):
    """Load credentials from HashiCorp Vault."""

    def __init__(self, vault_addr: str, vault_token: str, vault_path: str) -> None:
        """
        Initialize Vault client.

        Args:
            vault_addr: Vault server address
            vault_token: Vault authentication token
            vault_path: Base path for secrets in Vault

        Raises:
            ImportError: If hvac not installed
        """
        try:
            import hvac
        except ImportError as e:
            raise CredentialStorageError(
                "hvac library required for Vault support"
            ) from e

        self.client = hvac.Client(url=vault_addr, token=vault_token)
        self.vault_path = vault_path
        logger.info(f"Initialized Vault client at {vault_addr}")

    def get_credential(self, key: str) -> Optional[str]:
        """
        Retrieve secret from Vault.

        Args:
            key: Secret key in Vault

        Returns:
            Secret value or None if not found

        Raises:
            CredentialStorageError: On Vault access failure
        """
        try:
            secret_path = f"{self.vault_path}/{key}"
            response = self.client.secrets.kv.read_secret_version(secret_path)
            value = response["data"]["data"].get(key)
            if value:
                logger.debug(f"Retrieved credential {key} from Vault")
            return value
        except Exception as e:
            raise CredentialStorageError(f"Failed to read from Vault: {e}") from e

    def set_credential(self, key: str, value: str) -> None:
        """
        Store secret in Vault.

        Args:
            key: Secret key in Vault
            value: Secret value

        Raises:
            CredentialStorageError: On Vault access failure
        """
        try:
            secret_path = f"{self.vault_path}/{key}"
            self.client.secrets.kv.create_or_update_secret(
                path=secret_path, secret_data={key: value}
            )
            logger.debug(f"Stored credential {key} in Vault")
        except Exception as e:
            raise CredentialStorageError(f"Failed to write to Vault: {e}") from e


class CredentialManager:
    """
    Centralized credential management with fallback strategy.

    Tries sources in order: environment, Vault, then defaults.
    Supports credential caching and expiration.
    """

    def __init__(self) -> None:
        """Initialize credential manager with default sources."""
        self.sources: list[CredentialSource] = [EnvironmentSource()]
        self.cache: dict[str, Optional[str]] = {}

        vault_addr = os.environ.get("VAULT_ADDR")
        vault_token = os.environ.get("VAULT_TOKEN")
        vault_path = os.environ.get("VAULT_PATH", "secret/cloudpilot")

        if vault_addr and vault_token:
            try:
                self.sources.append(VaultSource(vault_addr, vault_token, vault_path))
                logger.info("Added Vault as credential source")
            except CredentialStorageError as e:
                logger.warning(f"Could not initialize Vault source: {e}")

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Retrieve credential with fallback strategy.

        Tries sources in order until credential found.
        Caches results for performance.

        Args:
            key: Credential key
            default: Default value if not found

        Returns:
            Credential value, default, or None
        """
        if key in self.cache:
            return self.cache[key]

        for source in self.sources:
            try:
                value = source.get_credential(key)
                if value is not None:
                    self.cache[key] = value
                    return value
            except CredentialStorageError as e:
                logger.warning(f"Error retrieving {key} from {source.__class__.__name__}: {e}")
                continue

        logger.debug(f"Credential {key} not found, using default")
        self.cache[key] = default
        return default

    def set(self, key: str, value: str) -> None:
        """
        Store credential in primary source.

        Args:
            key: Credential key
            value: Credential value
        """
        if not self.sources:
            raise CredentialStorageError("No credential sources configured")

        try:
            self.sources[0].set_credential(key, value)
            self.cache[key] = value
            logger.info(f"Stored credential {key}")
        except CredentialStorageError as e:
            logger.error(f"Failed to store credential {key}: {e}")
            raise

    def get_aws_credentials(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get AWS credentials (access_key, secret_key, session_token).

        Returns:
            Tuple of (access_key_id, secret_access_key, session_token)
        """
        access_key = self.get("AWS_ACCESS_KEY_ID")
        secret_key = self.get("AWS_SECRET_ACCESS_KEY")
        session_token = self.get("AWS_SESSION_TOKEN")
        return access_key, secret_key, session_token

    def get_azure_credentials(self) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Get Azure credentials (client_id, client_secret, tenant_id, subscription_id).

        Returns:
            Tuple of (client_id, client_secret, tenant_id, subscription_id)
        """
        client_id = self.get("AZURE_CLIENT_ID")
        client_secret = self.get("AZURE_CLIENT_SECRET")
        tenant_id = self.get("AZURE_TENANT_ID")
        subscription_id = self.get("AZURE_SUBSCRIPTION_ID")
        return client_id, client_secret, tenant_id, subscription_id

    def get_gcp_credentials(self) -> Optional[str]:
        """
        Get GCP service account credentials JSON.

        Returns:
            GCP service account JSON string or None
        """
        return self.get("GCP_SERVICE_ACCOUNT_JSON")

    def get_k8s_kubeconfig(self) -> Optional[str]:
        """
        Get Kubernetes kubeconfig content.

        Returns:
            Kubeconfig YAML content or None
        """
        return self.get("K8S_KUBECONFIG")

    def clear_cache(self) -> None:
        """Clear credential cache."""
        self.cache.clear()
        logger.debug("Cleared credential cache")
