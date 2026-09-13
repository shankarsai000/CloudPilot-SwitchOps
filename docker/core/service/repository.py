"""
Generic repository pattern implementing CRUD and querying on SQLAlchemy models.
"""

from typing import Any, Generic, List, Optional, Type, TypeVar
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic Repository encapsulating persistence logic for a given SQLAlchemy model.
    Decouples domain services and API routes from low-level database operations.
    """

    def __init__(self, model_cls: Type[ModelType], session: Session) -> None:
        self.model_cls = model_cls
        self.session = session

    def get_by_id(self, entity_id: Any) -> Optional[ModelType]:
        """Fetch an entity by primary key."""
        return self.session.get(self.model_cls, entity_id)

    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Fetch paginated list of entities."""
        stmt = select(self.model_cls).offset(skip).limit(limit)
        return list(self.session.scalars(stmt).all())

    def create(self, entity: ModelType) -> ModelType:
        """Persist a new entity."""
        self.session.add(entity)
        self.session.flush()
        return entity

    def update(self, entity: ModelType) -> ModelType:
        """Merge modifications into the active session."""
        merged = self.session.merge(entity)
        self.session.flush()
        return merged

    def delete(self, entity_id: Any) -> bool:
        """Delete an entity by ID."""
        entity = self.get_by_id(entity_id)
        if entity:
            self.session.delete(entity)
            self.session.flush()
            return True
        return False

    def count(self) -> int:
        """Return total row count."""
        stmt = select(func.count()).select_from(self.model_cls)
        result = self.session.scalar(stmt)
        return result or 0
