from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

default_args = {
    "owner": "de-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def extract_and_load():
    from extractors.api.example_api import ExampleApiExtractor
    from loaders.postgres_loader import PostgresLoader

    records = ExampleApiExtractor().extract()
    PostgresLoader().load(records, table="raw.example_items")


def run_dbt():
    import subprocess

    result = subprocess.run(
        [
            "dbt",
            "run",
            "--project-dir",
            "/opt/airflow/dbt",
            "--profiles-dir",
            "/opt/airflow/dbt",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    print(result.stdout)


with DAG(
    dag_id="example_pipeline",
    description="Extract from API → load to raw → dbt transform",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["example"],
) as dag:
    t_extract = PythonOperator(
        task_id="extract_and_load",
        python_callable=extract_and_load,
    )

    t_dbt = PythonOperator(
        task_id="dbt_run",
        python_callable=run_dbt,
    )

    t_extract >> t_dbt
