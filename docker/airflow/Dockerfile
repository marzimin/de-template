FROM apache/airflow:2.9.2-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean

USER airflow

# Install dbt and project dependencies inside Airflow image
COPY --chown=airflow:root requirements-airflow.txt /opt/airflow/
RUN pip install --no-cache-dir -r /opt/airflow/requirements-airflow.txt
