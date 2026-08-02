"""Abstract base class for all extractors."""

from abc import ABC, abstractmethod
from typing import Any


class BaseExtractor(ABC):
    """Abstract base class for all data extractors.

    Subclass this and implement ``extract`` to pull data from any source. The
    returned records are plain dicts ready for the loader layer, which squares
    up ragged keys and normalises the column names.

    Register the subclass under ``sources:`` in ``cfg/config.yaml`` and the
    example DAG picks it up with no import to wire in.
    """

    @abstractmethod
    def extract(self) -> list[dict[str, Any]]:
        """Pull data from the source and return a list of records."""
        ...
