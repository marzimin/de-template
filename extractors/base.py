from abc import ABC, abstractmethod
from typing import Any


class BaseExtractor(ABC):
    """Abstract base class for all data extractors.

    Subclass this and implement `extract` to pull data from any source.
    The returned records are plain dicts ready for the loader layer.
    """

    @abstractmethod
    def extract(self) -> list[dict[str, Any]]:
        """Pull data from the source and return a list of records."""
        ...
