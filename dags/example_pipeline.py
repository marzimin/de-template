"""Example end-to-end pipeline: extract → load → transform → export.

Copy this file for your own pipelines. Everything it needs to know — which
extractor to run, which table to write to, where dbt lives, what to export —
comes from ``cfg/config.yaml``, so adding a source is usually a configuration
change rather than a DAG change.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

SOURCE_NAME = "example_items"

default_args = {
    "owner": "de-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def extract_and_load(source_name: str) -> int:
    """Run one configured source's extractor and load its records into raw.

    The extractor is named in ``cfg/config.yaml`` as ``module:ClassName`` and
    imported here rather than at module scope: the DAG processor re-imports this
    file every few seconds just to rebuild the graph, and it should not pay for
    httpx, SQLAlchemy, and every extractor's dependencies to do that.

    Args:
        source_name: Key under ``sources:`` in the configuration.

    Returns:
        The number of rows loaded.

    Raises:
        KeyError: If the source is not configured.
    """
    from core.config import read_config
    from core.imports import import_from_path
    from loaders.postgres_loader import PostgresLoader

    config = read_config()
    sources = config.get("sources", {}) or {}
    if source_name not in sources:
        raise KeyError(
            f"Source {source_name!r} is not configured. Add it under `sources:` "
            "in cfg/config.yaml."
        )

    source = sources[source_name]
    extractor_class = import_from_path(source["extractor"])

    records = extractor_class().extract()
    loader = PostgresLoader(mode=source.get("load_mode", "append"))
    return loader.load(records, table=source["target_table"])


def run_dbt() -> None:
    """Run the dbt models against the warehouse.

    Raises:
        RuntimeError: If dbt exits non-zero. dbt reports model failures on
            stdout, so the output is printed before raising — with ``check=True``
            it would be buried in a CalledProcessError instead, where the task
            log does not show it.
    """
    import subprocess

    from core.config import dbt_paths, read_config

    paths = dbt_paths(read_config(), in_container=True)
    result = subprocess.run(
        [
            "dbt",
            "run",
            "--project-dir",
            paths["project_dir"],
            "--profiles-dir",
            paths["profiles_dir"],
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(
            f"dbt run failed with exit code {result.returncode}. See the output above."
        )


def export_marts() -> list[str]:
    """Export the configured marts to files for a downstream project.

    Returns:
        The paths written, as strings so they serialise into XCom cleanly.
    """
    from exporters.cli import export_all

    return [str(path) for path in export_all()]


with DAG(
    dag_id="example_pipeline",
    description="Extract from API → load to raw → dbt transform → export for DS",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["example"],
) as dag:
    t_extract = PythonOperator(
        task_id="extract_and_load",
        python_callable=extract_and_load,
        op_kwargs={"source_name": SOURCE_NAME},
    )

    t_dbt = PythonOperator(
        task_id="dbt_run",
        python_callable=run_dbt,
    )

    t_export = PythonOperator(
        task_id="export_marts",
        python_callable=export_marts,
    )

    t_extract >> t_dbt >> t_export
