"""
Generic service base class separating business workflows from persistence.
"""

from typing import Any, Generic, List, Optional, TypeVar

from core.database.base import Base
from core.errors import NotFoundError
from core.service.repository import BaseRepository

ModelType = TypeVar("ModelType", bound=Base)
RepoType = TypeVar("RepoType", bound=BaseRepository[Any])


class BaseService(Generic[ModelType, RepoType]):
    """
    Abstract domain service encapsulating business rules, transactions, and events.
    """

    def __init__(self, repository: RepoType) -> None:
        self.repository = repository

    def get_or_404(self, entity_id: Any) -> ModelType:
        """Fetch entity or raise NotFoundError."""
        entity = self.repository.get_by_id(entity_id)
        if not entity:
            raise NotFoundError(
                f"{self.repository.model_cls.__name__} with ID '{entity_id}' not found"
            )
        return entity

    def list_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Fetch a page of entities."""
        return self.repository.get_all(skip=skip, limit=limit)

    def create(self, entity: ModelType) -> ModelType:
        """Create and return a new entity."""
        return self.repository.create(entity)

    def delete(self, entity_id: Any) -> bool:
        """Delete an entity, raising 404 if not found."""
        self.get_or_404(entity_id)
        return self.repository.delete(entity_id)
