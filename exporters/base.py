"""Abstract base class for all exporters."""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseExporter(ABC):
    """Abstract base class for all data exporters.

    Subclass this and implement ``export`` to write warehouse data anywhere a
    downstream consumer can reach it: a local directory, object storage, a
    BI extract, another database.

    The counterpart to :class:`extractors.base.BaseExtractor` — that one brings
    data in, this one sends it out.
    """

    @abstractmethod
    def export(self) -> Path:
        """Write the data out and return the path it was written to."""
        ...
