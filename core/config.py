"""Project paths, environment, and YAML configuration.

Mirrors ``src/config.py`` in ds-template-local so the two projects resolve
configuration the same way. Table names, schema names, dbt directories, and
export destinations all live in ``cfg/config.yaml`` rather than being hardcoded
in DAGs and loaders.

This module stays free of heavy dependencies (no SQLAlchemy, no pyarrow) so
that anything needing only a path or a setting can import it cheaply.
"""

import logging
import os
import tomllib
from pathlib import Path
from typing import Any, cast

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_PROJECT_NAME = "de-template"


def _resolve_project_root() -> Path:
    """Locate the repository root that holds ``cfg/``, ``dbt/`` and ``data/``.

    Set ``DE_PROJECT_ROOT`` to override, which is how the container image and
    any non-standard checkout layout point at the right directory instead of
    relying on this file's depth on disk.

    Returns:
        Absolute path to the project root.
    """
    env_root = os.getenv("DE_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # .../<root>/core/config.py -> parents[1] is <root>
    return Path(__file__).resolve().parents[1]


#: Repository root: holds cfg/, dbt/, dags/, data/ and .env.
PROJECT_ROOT = _resolve_project_root()

# Load the single .env explicitly rather than relying on the current working
# directory, which differs between `make`, pytest, and an Airflow worker.
load_dotenv(PROJECT_ROOT / ".env")


def resolve_project_path(path: str | Path) -> Path:
    """Resolve a relative project path from the repository root.

    Args:
        path: Absolute path (returned unchanged) or a path relative to the root.

    Returns:
        An absolute path.
    """
    project_path = Path(path)
    if project_path.is_absolute():
        return project_path
    return PROJECT_ROOT / project_path


def read_config() -> dict[str, Any]:
    """Read ``cfg/config.yaml`` and return its contents.

    Returns:
        Parsed configuration settings.
    """
    config_file_path = resolve_project_path(Path("cfg") / "config.yaml")
    with open(config_file_path, encoding="utf-8") as file:
        config_data = yaml.safe_load(file)
    return cast(dict[str, Any], config_data or {})


def project_name() -> str:
    """Return the project name declared in ``pyproject.toml``.

    Used to derive defaults so that renaming the project in one place renames
    everything downstream, rather than leaving placeholders scattered through
    the configuration.

    Returns:
        The ``[project].name`` value, or :data:`DEFAULT_PROJECT_NAME` if the
        manifest is missing or does not declare one.
    """
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as file:
            manifest = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        logger.warning(
            "Could not read %s; falling back to project name %r.",
            pyproject_path,
            DEFAULT_PROJECT_NAME,
        )
        return DEFAULT_PROJECT_NAME

    name = manifest.get("project", {}).get("name")
    return str(name) if name else DEFAULT_PROJECT_NAME


def warehouse_schemas(config: dict[str, Any]) -> dict[str, str]:
    """Return the configured warehouse schema names.

    A single accessor so the fallbacks live in one place rather than being
    repeated at each call site, where the copies can drift apart.

    Args:
        config: Parsed ``cfg/config.yaml`` contents.

    Returns:
        Mapping of layer name (``raw``, ``staging``, ``marts``) to schema name.
    """
    configured = config.get("warehouse", {}) or {}
    return {
        "raw": str(configured.get("raw_schema", "raw")),
        "staging": str(configured.get("staging_schema", "staging")),
        "marts": str(configured.get("marts_schema", "marts")),
    }


def dbt_paths(config: dict[str, Any], in_container: bool = False) -> dict[str, str]:
    """Return the dbt project and profiles directories.

    The paths differ between a laptop (relative to the repository root) and an
    Airflow worker (the mounted ``/opt/airflow/dbt``), which is why the DAG
    should ask for them rather than hardcoding either.

    Args:
        config: Parsed ``cfg/config.yaml`` contents.
        in_container: Return the container paths instead of the local ones.

    Returns:
        Mapping with ``project_dir`` and ``profiles_dir`` keys.
    """
    configured = config.get("dbt", {}) or {}
    if in_container:
        container_dir = str(configured.get("container_dir", "/opt/airflow/dbt"))
        return {"project_dir": container_dir, "profiles_dir": container_dir}

    project_dir = str(resolve_project_path(configured.get("project_dir", "dbt")))
    profiles_dir = str(resolve_project_path(configured.get("profiles_dir", "dbt")))
    return {"project_dir": project_dir, "profiles_dir": profiles_dir}
