"""
Ownership Mapper — Resolves application ownership.

Determines application ownership by analyzing resource tags,
K8s annotations, naming conventions, and team registries.
Produces ownership mappings with confidence scores.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models_application import Application, EnvironmentType, OwnershipInfo
from models_ownership import (
    EscalationContact,
    OwnershipMapping,
    OwnershipReport,
    TeamInfo,
)
from models_resource import CloudResource

logger = logging.getLogger(__name__)


class OwnershipMapper:
    """Resolves application ownership from multiple data sources.

    Resolution sources (in priority order):
    1. Resource tags (owner, team, contact)
    2. K8s annotations (app.kubernetes.io/managed-by)
    3. Team registry (external team database)
    4. Naming convention heuristics
    """

    # Tag keys used to resolve ownership (priority order)
    OWNER_TAG_KEYS: list[str] = [
        "owner",
        "Owner",
        "team",
        "Team",
        "contact",
        "Contact",
        "maintainer",
        "Maintainer",
        "managed-by",
        "ManagedBy",
    ]

    TEAM_TAG_KEYS: list[str] = [
        "team",
        "Team",
        "department",
        "Department",
        "business-unit",
        "BusinessUnit",
        "cost-center",
        "CostCenter",
    ]

    REPO_TAG_KEYS: list[str] = [
        "repository",
        "Repository",
        "repo",
        "Repo",
        "source",
        "Source",
        "git-repo",
    ]

    ENVIRONMENT_TAG_KEYS: list[str] = [
        "env",
        "environment",
        "Environment",
        "Env",
        "stage",
        "Stage",
    ]

    def __init__(
        self,
        team_registry: Optional[dict[str, TeamInfo]] = None,
    ) -> None:
        """Initialize ownership mapper.

        Args:
            team_registry: Optional team name → TeamInfo mapping
        """
        self._team_registry: dict[str, TeamInfo] = team_registry or {}
        logger.info(
            "OwnershipMapper initialized with %d registered teams",
            len(self._team_registry),
        )

    def register_team(self, team: TeamInfo) -> None:
        """Register a team in the team registry.

        Args:
            team: TeamInfo to register
        """
        self._team_registry[team.team_name.lower()] = team
        logger.debug("Registered team: %s", team.team_name)

    def map_ownership(
        self,
        applications: list[Application],
        resources: list[CloudResource],
    ) -> list[OwnershipMapping]:
        """Resolve ownership for all applications.

        Args:
            applications: Discovered applications
            resources: M1 cloud resources for tag analysis

        Returns:
            List of OwnershipMapping objects
        """
        resource_map = {r.id: r for r in resources}
        mappings: list[OwnershipMapping] = []

        for app in applications:
            mapping = self._resolve_ownership(app, resource_map)
            mappings.append(mapping)

            # Attach to application model
            app.ownership = OwnershipInfo(
                owner=mapping.primary_owner,
                team=mapping.team.team_name if mapping.team else None,
                team_id=mapping.team.team_id if mapping.team else None,
                slack_channel=mapping.team.slack_channel if mapping.team else None,
                email=mapping.team.email if mapping.team else None,
                repository=self._extract_tag_value(app, resource_map, self.REPO_TAG_KEYS),
                business_unit=mapping.team.business_unit if mapping.team else None,
                cost_center=mapping.team.cost_center if mapping.team else None,
                environment=app.environment,
                pagerduty_service=mapping.team.pagerduty_service_id if mapping.team else None,
                confidence=mapping.confidence,
            )

        logger.info(
            "Ownership mapping complete: %d applications, %d with owners",
            len(mappings),
            sum(1 for m in mappings if m.primary_owner),
        )
        return mappings

    def get_coverage_report(
        self, mappings: list[OwnershipMapping]
    ) -> OwnershipReport:
        """Generate ownership coverage report.

        Args:
            mappings: Ownership mappings to analyze

        Returns:
            OwnershipReport with coverage statistics
        """
        total = len(mappings)
        owned = sum(1 for m in mappings if m.primary_owner or m.team)
        unowned = total - owned

        by_team: dict[str, int] = {}
        by_source: dict[str, int] = {}
        confidence_sum: float = 0.0
        unverified: int = 0

        for mapping in mappings:
            team_name = mapping.team.team_name if mapping.team else "unowned"
            by_team[team_name] = by_team.get(team_name, 0) + 1
            by_source[mapping.resolution_source] = (
                by_source.get(mapping.resolution_source, 0) + 1
            )
            confidence_sum += mapping.confidence
            if not mapping.verified:
                unverified += 1

        coverage = (owned / total * 100) if total > 0 else 0.0
        avg_confidence = (confidence_sum / total) if total > 0 else 0.0

        return OwnershipReport(
            total_applications=total,
            owned_applications=owned,
            unowned_applications=unowned,
            coverage_percentage=round(coverage, 1),
            average_confidence=round(avg_confidence, 3),
            by_team=by_team,
            by_resolution_source=by_source,
            unverified_count=unverified,
            mappings=mappings,
        )

    def _resolve_ownership(
        self,
        app: Application,
        resource_map: dict[str, CloudResource],
    ) -> OwnershipMapping:
        """Resolve ownership for a single application.

        Tries sources in priority order:
        1. Tags (highest confidence)
        2. K8s annotations
        3. Team registry lookup
        4. Naming convention

        Args:
            app: Application to resolve
            resource_map: Resource ID → CloudResource mapping

        Returns:
            OwnershipMapping with best-effort resolution
        """
        # Phase 1: Extract from tags
        owner = self._extract_tag_value(app, resource_map, self.OWNER_TAG_KEYS)
        team_name = self._extract_tag_value(app, resource_map, self.TEAM_TAG_KEYS)

        if owner or team_name:
            team_info = self._lookup_team(team_name) if team_name else None
            return OwnershipMapping(
                application_id=app.application_id,
                application_name=app.name,
                team=team_info,
                primary_owner=owner,
                confidence=0.9 if owner and team_name else 0.7,
                resolution_source="tag",
            )

        # Phase 2: K8s annotations
        owner, team_name = self._extract_from_annotations(app, resource_map)
        if owner or team_name:
            team_info = self._lookup_team(team_name) if team_name else None
            return OwnershipMapping(
                application_id=app.application_id,
                application_name=app.name,
                team=team_info,
                primary_owner=owner,
                confidence=0.8 if owner and team_name else 0.6,
                resolution_source="annotation",
            )

        # Phase 3: Team registry (fuzzy match on app name)
        team_info = self._fuzzy_team_lookup(app.name)
        if team_info:
            return OwnershipMapping(
                application_id=app.application_id,
                application_name=app.name,
                team=team_info,
                primary_owner=team_info.manager,
                confidence=0.5,
                resolution_source="registry",
            )

        # Phase 4: No ownership found
        return OwnershipMapping(
            application_id=app.application_id,
            application_name=app.name,
            confidence=0.0,
            resolution_source="unknown",
        )

    def _extract_tag_value(
        self,
        app: Application,
        resource_map: dict[str, CloudResource],
        tag_keys: list[str],
    ) -> Optional[str]:
        """Extract a tag value from application's resources.

        Args:
            app: Application
            resource_map: Resource mapping
            tag_keys: Tag keys to search (in priority order)

        Returns:
            Tag value or None
        """
        # Check application-level tags first
        for key in tag_keys:
            if key in app.tags and app.tags[key].strip():
                return app.tags[key].strip()

        # Check individual resource tags
        for resource_id in app.resource_ids:
            resource = resource_map.get(resource_id)
            if not resource:
                continue
            for key in tag_keys:
                if key in resource.tags and resource.tags[key].strip():
                    return resource.tags[key].strip()

        return None

    def _extract_from_annotations(
        self,
        app: Application,
        resource_map: dict[str, CloudResource],
    ) -> tuple[Optional[str], Optional[str]]:
        """Extract ownership from K8s annotations.

        Args:
            app: Application
            resource_map: Resource mapping

        Returns:
            Tuple of (owner, team_name)
        """
        annotation_keys_owner = [
            "app.kubernetes.io/managed-by",
            "team.cloudpilot.ai/owner",
        ]
        annotation_keys_team = [
            "team.cloudpilot.ai/team",
            "app.kubernetes.io/part-of",
        ]

        owner: Optional[str] = None
        team_name: Optional[str] = None

        for resource_id in app.resource_ids:
            resource = resource_map.get(resource_id)
            if not resource:
                continue

            annotations = resource.metadata.get("annotations", {})
            if not isinstance(annotations, dict):
                continue

            for key in annotation_keys_owner:
                if key in annotations and annotations[key].strip():
                    owner = annotations[key].strip()
                    break

            for key in annotation_keys_team:
                if key in annotations and annotations[key].strip():
                    team_name = annotations[key].strip()
                    break

            if owner or team_name:
                break

        return owner, team_name

    def _lookup_team(self, team_name: Optional[str]) -> Optional[TeamInfo]:
        """Look up team in registry by name.

        Args:
            team_name: Team name to look up

        Returns:
            TeamInfo or None
        """
        if not team_name:
            return None

        normalized = team_name.lower().strip()

        if normalized in self._team_registry:
            return self._team_registry[normalized]

        # Try partial match
        for key, team_info in self._team_registry.items():
            if normalized in key or key in normalized:
                return team_info

        return None

    def _fuzzy_team_lookup(self, app_name: str) -> Optional[TeamInfo]:
        """Fuzzy-match application name to team registry.

        Args:
            app_name: Application name

        Returns:
            Matching TeamInfo or None
        """
        app_lower = app_name.lower()

        for team_name, team_info in self._team_registry.items():
            # Check if app name contains team name or vice versa
            if team_name in app_lower or app_lower in team_name:
                return team_info

            # Check team repositories
            for repo in team_info.repositories:
                repo_lower = repo.lower()
                if app_lower in repo_lower:
                    return team_info

        return None
