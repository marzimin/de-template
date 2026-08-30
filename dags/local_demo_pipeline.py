"""Local demo pipeline: extract (local files) → load → transform → export.

The no-external-services counterpart to ``dags/example_pipeline.py`` — same
shape (extract → load → dbt → export), but every source reads from
``data/sample_source/`` instead of a real API, so this runs end to end with
nothing to configure. Use it to see the whole ELT process work, then inspect,
amend, and re-run any piece of it. See docs/pipelines.md
("Local dummy data") for the full picture and what this data does and
doesn't prove.

Before triggering this DAG for the first time, seed the demo data:

    make local-seed

Re-run that at any point to advance ``latest_orders.xlsx``, grow
``customers.xlsx``, and (once a month) add a new ``monthly_sales_*.xlsx`` —
then re-trigger this DAG to pick up the changes.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

#: Every `local_*` source in cfg/config.yaml — one extract-and-load task
#: each, all independent of one another, all feeding the same dbt run.
SOURCE_NAMES = [
    "local_seed_data",
    "local_latest_orders",
    "local_customers",
    "local_monthly_sales",
]

default_args = {
    "owner": "de-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def extract_and_load(source_name: str) -> int:
    """Run one configured source's extractor and load its records into raw.

    Identical to ``dags/example_pipeline.py``'s task of the same name —
    duplicated rather than imported, so each DAG file stays a single,
    self-contained copy-paste starting point. See that file for the
    "why inside the function, not module scope" note.

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


def run_dbt(command: str) -> None:
    """Run a dbt subcommand (``run`` or ``test``) against the warehouse.

    Args:
        command: ``"run"`` or ``"test"``.

    Raises:
        RuntimeError: If dbt exits non-zero. dbt reports failures on stdout,
            so the output is printed before raising — with ``check=True`` it
            would be buried in a CalledProcessError instead, where the task
            log does not show it.
    """
    import subprocess

    from core.config import dbt_paths, read_config

    paths = dbt_paths(read_config(), in_container=True)
    result = subprocess.run(
        [
            "dbt",
            command,
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
            f"dbt {command} failed with exit code {result.returncode}. "
            "See the output above."
        )


def export_marts() -> list[str]:
    """Export the configured marts to files for a downstream project.

    Returns:
        The paths written, as strings so they serialise into XCom cleanly.
    """
    from exporters.cli import export_all

    return [str(path) for path in export_all()]


with DAG(
    dag_id="local_demo_pipeline",
    description=(
        "Extract from data/sample_source/ → load to raw → dbt transform "
        "→ test → export. No external services required."
    ),
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["demo", "local"],
) as dag:
    t_extract = [
        PythonOperator(
            task_id=f"extract_and_load__{source_name}",
            python_callable=extract_and_load,
            op_kwargs={"source_name": source_name},
        )
        for source_name in SOURCE_NAMES
    ]

    t_dbt_run = PythonOperator(
        task_id="dbt_run",
        python_callable=run_dbt,
        op_kwargs={"command": "run"},
    )

    t_dbt_test = PythonOperator(
        task_id="dbt_test",
        python_callable=run_dbt,
        op_kwargs={"command": "test"},
    )

    t_export = PythonOperator(
        task_id="export_marts",
        python_callable=export_marts,
    )

    t_extract >> t_dbt_run >> t_dbt_test >> t_export
