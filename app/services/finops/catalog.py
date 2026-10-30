"""
CloudPilot SwitchOps — Versioned FinOps Pricing Catalog

Loads and indexes demonstration cloud pricing data from versioned JSON catalogs.
Guarantees transparent unit rates, catalog provenance, and decimal pricing.
"""

from __future__ import annotations

from decimal import Decimal
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cloudpilot.finops.catalog")

DEFAULT_CATALOG_PATH = Path("data/pricing/catalog-v1.json")


class PricingRateEntry:
    """Immutable rate specification for a single cloud SKU or container configuration."""

    def __init__(
        self,
        provider: str,
        region: str,
        sku: str,
        resource_type: str,
        pricing_unit: str,
        unit_price: Decimal,
        currency: str,
        description: str,
    ) -> None:
        self.provider = provider
        self.region = region
        self.sku = sku
        self.resource_type = resource_type
        self.pricing_unit = pricing_unit
        self.unit_price = unit_price
        self.currency = currency
        self.description = description

    def __repr__(self) -> str:
        return f"<PricingRateEntry {self.sku} ({self.region}): {self.unit_price} {self.currency}/{self.pricing_unit}>"


class PricingCatalog:
    """Loads, validates, and queries versioned pricing catalogs."""

    def __init__(self, catalog_path: Optional[Path] = None) -> None:
        self.path = catalog_path or DEFAULT_CATALOG_PATH
        self.catalog_version: str = "1.0"
        self.currency: str = "USD"
        self.standard_monthly_hours: int = 730
        self.provenance: Dict[str, Any] = {}
        self._rates_by_sku: Dict[str, PricingRateEntry] = {}
        self._rates_by_provider_type: Dict[str, List[PricingRateEntry]] = {}
        self.load_catalog()

    def load_catalog(self) -> None:
        """Read and index rates from catalog JSON file."""
        if not self.path.exists():
            logger.warning("Pricing catalog file not found at '%s'. FinOps engine running without catalog.", self.path)
            return

        try:
            raw_text = self.path.read_text(encoding="utf-8")
            data = json.loads(raw_text)

            self.catalog_version = data.get("catalog_version", "1.0")
            self.currency = data.get("currency", "USD")
            self.provenance = data.get("provenance", {})
            self.standard_monthly_hours = int(self.provenance.get("standard_monthly_hours", 730))

            rates_list = data.get("rates", [])
            for r in rates_list:
                sku = r.get("sku", "")
                entry = PricingRateEntry(
                    provider=r.get("provider", "unknown"),
                    region=r.get("region", "global"),
                    sku=sku,
                    resource_type=r.get("resource_type", "other"),
                    pricing_unit=r.get("pricing_unit", "hour"),
                    unit_price=Decimal(str(r.get("unit_price", "0.0000"))),
                    currency=r.get("currency", "USD"),
                    description=r.get("description", ""),
                )
                self._rates_by_sku[sku] = entry

                prov_key = f"{entry.provider}:{entry.resource_type}"
                if prov_key not in self._rates_by_provider_type:
                    self._rates_by_provider_type[prov_key] = []
                self._rates_by_provider_type[prov_key].append(entry)

            logger.info(
                "Loaded pricing catalog v%s with %d SKUs from %s",
                self.catalog_version,
                len(self._rates_by_sku),
                self.path,
            )
        except Exception as exc:
            logger.error("Failed to load pricing catalog '%s': %s", self.path, exc)

    def get_rate_for_sku(self, sku: str) -> Optional[PricingRateEntry]:
        """Lookup rate entry by exact SKU identifier."""
        return self._rates_by_sku.get(sku)

    def find_rate(
        self,
        provider: str,
        resource_type: str,
        subtype: Optional[str] = None,
    ) -> Optional[PricingRateEntry]:
        """
        Find rate by provider, resource type, and subtype (e.g. aws, aws_instance, t3.micro).
        """
        if subtype:
            exact_sku = f"{resource_type}:{subtype}"
            if exact_sku in self._rates_by_sku:
                return self._rates_by_sku[exact_sku]

        # Check default fallback
        fallback_sku = f"{resource_type}:standard"
        if fallback_sku in self._rates_by_sku:
            return self._rates_by_sku[fallback_sku]

        return None
