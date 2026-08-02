"""Command line entry point for the warehouse → file hand-off.

Run with ``make export`` (or ``python -m exporters.cli``). Exports every dataset
listed under ``exports.datasets`` in ``cfg/config.yaml``.
"""

import argparse
import logging
import os
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.engine import Engine

from core.config import read_config, resolve_project_path, warehouse_schemas
from exporters.mart_exporter import ExportFormat, MartExporter
from exporters.serialisation import DEFAULT_NULL_SENTINEL

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

log = structlog.get_logger()


def export_destination(config: dict[str, Any]) -> Path:
    """Resolve where exported files are written.

    ``DS_DATA_RAW_DIR`` wins when set, which is how you point this project
    straight at ds-template's ``data/raw/`` without editing tracked
    configuration. Otherwise ``exports.destination`` applies, resolved from the
    repository root.

    Args:
        config: Parsed ``cfg/config.yaml`` contents.

    Returns:
        Absolute destination directory.
    """
    env_destination = os.getenv("DS_DATA_RAW_DIR")
    if env_destination:
        return Path(env_destination).expanduser().resolve()

    exports = config.get("exports", {}) or {}
    return resolve_project_path(exports.get("destination", "data/exports"))


def export_all(
    config: dict[str, Any] | None = None,
    engine: Engine | None = None,
) -> list[Path]:
    """Export every dataset configured under ``exports.datasets``.

    Args:
        config: Parsed configuration. Read from disk when omitted.
        engine: Warehouse engine, shared across datasets. Built from the
            environment when omitted.

    Returns:
        The paths written, in configuration order.
    """
    config = config if config is not None else read_config()
    exports = config.get("exports", {}) or {}
    datasets = exports.get("datasets", []) or []

    if not datasets:
        log.warning(
            "export_skipped", reason="no datasets configured in cfg/config.yaml"
        )
        return []

    destination = export_destination(config)
    export_format: ExportFormat = exports.get("format", "csv")
    null_sentinel = str(exports.get("null_sentinel", DEFAULT_NULL_SENTINEL))
    marts_schema = warehouse_schemas(config)["marts"]

    written: list[Path] = []
    for dataset in datasets:
        exporter = MartExporter(
            relation=dataset["relation"],
            destination=destination,
            file_name=dataset.get("file_name"),
            export_format=export_format,
            default_schema=marts_schema,
            engine=engine,
            null_sentinel=null_sentinel,
        )
        written.append(exporter.export())
        # Reuse one engine across datasets rather than opening a pool per file.
        engine = exporter.engine

    return written


def main() -> None:
    """Export the configured marts, optionally filtered to one dataset."""
    parser = argparse.ArgumentParser(
        prog="export",
        description=(
            "Export warehouse marts to files for downstream consumers such as "
            "ds-template. Datasets are configured in cfg/config.yaml."
        ),
    )
    parser.add_argument(
        "--relation",
        help=(
            "Export a single relation (schema.table) instead of everything in "
            "cfg/config.yaml. Useful for a one-off pull."
        ),
    )
    args = parser.parse_args()

    config = read_config()

    exports = config.get("exports", {}) or {}

    if args.relation:
        exporter = MartExporter(
            relation=args.relation,
            destination=export_destination(config),
            export_format=exports.get("format", "csv"),
            default_schema=warehouse_schemas(config)["marts"],
            null_sentinel=str(exports.get("null_sentinel", DEFAULT_NULL_SENTINEL)),
        )
        paths = [exporter.export()]
    else:
        paths = export_all(config)

    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
