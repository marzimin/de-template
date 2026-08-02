"""Every DAG file must import cleanly and produce a valid DAG.

A DAG that fails to parse does not error loudly — it just never appears in the
Airflow UI, and you find out when the data does not arrive. This is the cheapest
possible guard against that.
"""

import inspect
from pathlib import Path

import pytest

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
DAG_FILES = sorted(
    path for path in DAGS_DIR.glob("*.py") if not path.name.startswith("_")
)


@pytest.fixture(scope="module")
def dag_bag():
    airflow_models = pytest.importorskip(
        "airflow.models",
        reason="apache-airflow is not installed in this environment",
    )
    # `include_examples` was removed in Airflow 3.3; examples are off by default
    # there. Pass it only when the running version still accepts it, so this
    # suite works either side of the change.
    parameters = inspect.signature(airflow_models.DagBag.__init__).parameters
    kwargs = {"include_examples": False} if "include_examples" in parameters else {}
    return airflow_models.DagBag(dag_folder=str(DAGS_DIR), **kwargs)


def test_there_is_at_least_one_dag_file():
    assert DAG_FILES, "expected at least the bundled example DAG in dags/"


def test_no_dag_has_an_import_error(dag_bag):
    assert not dag_bag.import_errors, (
        f"DAG files failed to parse: {dag_bag.import_errors}"
    )


def test_the_example_pipeline_is_registered(dag_bag):
    assert "example_pipeline" in dag_bag.dags


def test_the_example_pipeline_runs_extract_then_transform_then_export(dag_bag):
    dag = dag_bag.dags["example_pipeline"]

    assert set(dag.task_ids) == {"extract_and_load", "dbt_run", "export_marts"}
    assert dag.get_task("dbt_run").upstream_task_ids == {"extract_and_load"}
    assert dag.get_task("export_marts").upstream_task_ids == {"dbt_run"}
