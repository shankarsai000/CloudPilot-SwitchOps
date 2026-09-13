"""
Repository and service patterns for clean architectural separation.
"""

from core.service.repository import BaseRepository
from core.service.service import BaseService

__all__ = [
    "BaseRepository",
    "BaseService",
]
