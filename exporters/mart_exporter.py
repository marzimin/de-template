"""Export a warehouse relation to a CSV or Parquet file on disk."""

import csv
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Literal

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from core.warehouse import engine_from_env, split_relation
from exporters.base import BaseExporter
from exporters.serialisation import DEFAULT_NULL_SENTINEL, csv_row, parquet_row

log = structlog.get_logger()

ExportFormat = Literal["csv", "parquet"]

#: Rows fetched per round trip. Large enough to keep the round-trip count down,
#: small enough that a wide mart does not blow up the worker's memory.
CHUNK_SIZE = 10_000


class MartExporter(BaseExporter):
    """Reads one warehouse relation and writes it to a single file.

    The output is what ds-template-local consumes: point that project's
    ``cfg/config.yaml`` at ``data.input_file`` matching ``file_name`` here.

    Usage:
        exporter = MartExporter("marts.example_items", Path("data/exports"))
        path = exporter.export()
    """

    def __init__(
        self,
        relation: str,
        destination: Path,
        file_name: str | None = None,
        export_format: ExportFormat = "csv",
        default_schema: str = "marts",
        engine: Engine | None = None,
        null_sentinel: str = DEFAULT_NULL_SENTINEL,
    ) -> None:
        """Configure an export.

        Args:
            relation: The relation to read, as ``schema.table`` or ``table``.
            destination: Directory to write into. Created if absent.
            file_name: Output file name. Defaults to the table name plus an
                extension matching ``export_format``.
            export_format: ``"csv"`` or ``"parquet"``.
            default_schema: Schema assumed when ``relation`` is unqualified.
            engine: Warehouse engine. Built from the environment when omitted.
            null_sentinel: What a SQL NULL becomes in CSV output. Ignored for
                Parquet, which has a real null.

        Raises:
            ValueError: If ``export_format`` is not a supported format.
        """
        if export_format not in ("csv", "parquet"):
            raise ValueError(
                f"Unsupported export format {export_format!r}. Use 'csv' or 'parquet'."
            )

        self.schema, self.table = split_relation(relation, default_schema)
        self.destination = destination
        self.export_format: ExportFormat = export_format
        self.file_name = file_name or f"{self.table}.{export_format}"
        self.engine = engine or engine_from_env()
        self.null_sentinel = null_sentinel

    @property
    def output_path(self) -> Path:
        """The full path this exporter writes to."""
        return self.destination / self.file_name

    def _read_chunks(self) -> Iterator[tuple[Sequence[str], list[dict[str, Any]]]]:
        """Stream the relation in chunks of :data:`CHUNK_SIZE` rows.

        Yields:
            A ``(column_names, rows)`` pair per chunk. Emits one empty chunk for
            an empty relation so callers still learn the column names and can
            write a header-only file.
        """
        # Identifiers are validated by split_relation; bind parameters are not
        # available for table names, so interpolation is the only option here.
        query = text(f"SELECT * FROM {self.schema}.{self.table}")

        with self.engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(query)
            columns = list(result.keys())
            emitted = False
            while True:
                rows = result.fetchmany(CHUNK_SIZE)
                if not rows:
                    break
                emitted = True
                yield columns, [dict(row._mapping) for row in rows]
            if not emitted:
                yield columns, []

    def _write_csv(self) -> Path:
        """Write the relation to CSV, streaming chunk by chunk."""
        path = self.output_path
        row_count = 0

        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer: csv.DictWriter[str] | None = None
            for columns, rows in self._read_chunks():
                if writer is None:
                    writer = csv.DictWriter(handle, fieldnames=list(columns))
                    writer.writeheader()
                # Every value is converted explicitly. Handing the driver's
                # objects straight to the writer would fall back to str(), which
                # destroys binary columns and emits invalid JSON.
                writer.writerows(
                    csv_row(row, columns, self.null_sentinel) for row in rows
                )
                row_count += len(rows)

        return self._finish(path, row_count)

    def _write_parquet(self) -> Path:
        """Write the relation to Parquet.

        Unlike the CSV path this buffers the whole relation in memory: Parquet
        needs a schema up front, and inferring one from a first chunk would
        break on a later chunk whose all-null column types disagree. Fine for
        marts that fit in memory, which is what a template ships for; swap in a
        typed ``pyarrow.schema`` and a ``ParquetWriter`` if yours does not.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = self.output_path
        columns: Sequence[str] = []
        all_rows: list[dict[str, Any]] = []
        for chunk_columns, rows in self._read_chunks():
            columns = chunk_columns
            all_rows.extend(parquet_row(row, columns) for row in rows)

        if all_rows:
            table = pa.Table.from_pylist(all_rows)
        else:
            # from_pylist([]) yields a table with no columns at all, which loses
            # the schema. Build the empty table from the column names instead.
            table = pa.table(
                {column: pa.array([], type=pa.string()) for column in columns}
            )

        pq.write_table(table, path)
        return self._finish(path, len(all_rows))

    def _finish(self, path: Path, row_count: int) -> Path:
        """Log a completed export and return its path."""
        log.info(
            "export_complete",
            relation=f"{self.schema}.{self.table}",
            path=str(path),
            format=self.export_format,
            rows=row_count,
        )
        return path

    def export(self) -> Path:
        """Read the relation and write it to :attr:`output_path`.

        Returns:
            The path written to.
        """
        self.destination.mkdir(parents=True, exist_ok=True)
        log.info(
            "export_started",
            relation=f"{self.schema}.{self.table}",
            path=str(self.output_path),
            format=self.export_format,
        )

        if self.export_format == "parquet":
            return self._write_parquet()
        return self._write_csv()
