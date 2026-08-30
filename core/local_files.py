"""A folder of files on local disk, addressed the way a cloud drive API would be.

Used by ``extractors/files/local_excel.py`` and the generators in
``scripts/seed_toolkit.py``/``scripts/demo_dataset.py`` to exercise the
pipeline end to end (extract → load → dbt → export) with no network call and
no external account — for local development, tests, and CI.

This is a development convenience, not a production data source. There is no
auth because there is nothing to authenticate to. If you later add a real
extractor for a live service (see ``extractors/api/example_api.py`` for that
pattern), it does not need to share this module — build its own client and
point a separate source at it in ``cfg/config.yaml``.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from core.config import read_config, resolve_project_path

log = structlog.get_logger()

#: Falls back to here when cfg/config.yaml has no `local_dummy_data:` section.
DEFAULT_DESTINATION = "data/sample_source"
DEFAULT_FOLDER_PATH = "Sample Data"


def _iso_modified(path: Path) -> str:
    """Format a file's modification time as UTC ISO-8601, seconds precision."""
    return (
        datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class LocalFolderClient:
    """A folder of files on local disk, addressed by path relative to a root directory.

    Item ids are the file's path relative to ``base_dir`` (POSIX-style, e.g.
    ``Sample Data/customers.xlsx``). They only ever need to round-trip through
    :meth:`download`, so any stable, unique string works.

    Usage:
        client = LocalFolderClient.from_config()
        for item in client.list_children("Sample Data"):
            content = client.download(item["id"])
    """

    def __init__(self, base_dir: Path) -> None:
        """Configure the client. Prefer :meth:`from_config` over calling this directly.

        Args:
            base_dir: Directory that stands in for the drive root. Created on
                first write if it does not exist.
        """
        self._base_dir = base_dir

    @classmethod
    def from_config(cls) -> "LocalFolderClient":
        """Build a client from ``local_dummy_data.destination`` in ``cfg/config.yaml``.

        No required settings — a local path is not a secret, so it lives in
        the tracked config file with a sensible default, the same way
        ``exports.destination`` does.

        Returns:
            A configured client, pointed at the resolved destination directory.
        """
        local_config = read_config().get("local_dummy_data", {}) or {}
        destination = local_config.get("destination", DEFAULT_DESTINATION)
        return cls(base_dir=resolve_project_path(destination))

    def _resolve(self, folder_path: str) -> Path:
        return self._base_dir / folder_path.strip("/")

    def list_children(self, folder_path: str) -> list[dict[str, Any]]:
        """List the items in a folder.

        Args:
            folder_path: Folder path relative to :attr:`_base_dir`.

        Returns:
            One dict per item (file or subfolder) — ``id``, ``name``, and
            either a ``file`` or ``folder`` marker key, plus
            ``lastModifiedDateTime`` for files. An unresolved folder is
            treated as empty rather than an error, the way a freshly seeded
            project has not written anything yet.
        """
        folder = self._resolve(folder_path)
        if not folder.is_dir():
            return []

        items = []
        for path in sorted(folder.iterdir()):
            item_id = str(path.relative_to(self._base_dir))
            if path.is_dir():
                items.append({"id": item_id, "name": path.name, "folder": {}})
            else:
                items.append(
                    {
                        "id": item_id,
                        "name": path.name,
                        "file": {},
                        "lastModifiedDateTime": _iso_modified(path),
                    }
                )
        return items

    def download(self, item_id: str) -> bytes:
        """Read a file's raw content by the id from :meth:`list_children`.

        Args:
            item_id: Path relative to :attr:`_base_dir`, from
                :meth:`list_children`.

        Returns:
            The file's bytes.
        """
        log.info("local_download", item_id=item_id)
        return (self._base_dir / item_id).read_bytes()

    def upload_file(
        self, folder_path: str, file_name: str, content: bytes
    ) -> dict[str, Any]:
        """Write (or overwrite) a file in a folder, creating the folder if needed.

        Args:
            folder_path: Destination folder, relative to :attr:`_base_dir`.
            file_name: Name to give the file.
            content: Raw file bytes.

        Returns:
            The written item, shaped like the dicts from :meth:`list_children`.
        """
        folder = self._resolve(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / file_name
        target.write_bytes(content)
        log.info("local_upload", folder_path=folder_path, file_name=file_name)
        return {
            "id": str(target.relative_to(self._base_dir)),
            "name": file_name,
            "file": {},
            "lastModifiedDateTime": _iso_modified(target),
        }


def default_folder_path() -> str:
    """Return ``local_dummy_data.folder_path`` from ``cfg/config.yaml``, or the default."""
    local_config = read_config().get("local_dummy_data", {}) or {}
    return str(local_config.get("folder_path", DEFAULT_FOLDER_PATH))
