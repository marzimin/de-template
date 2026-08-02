FROM apache/airflow:3.1.8-python3.12

ARG VERSION=dev
LABEL org.opencontainers.image.version="${VERSION}"

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install dbt and the project's runtime dependencies inside the Airflow image.
# Kept in step with pyproject.toml by tests/test_requirements_sync.py.
COPY --chown=airflow:root requirements-airflow.txt /opt/airflow/
RUN pip install --no-cache-dir -r /opt/airflow/requirements-airflow.txt

# Bake the project source in so the published image runs standalone. Under
# docker compose these paths are shadowed by bind mounts, which is what makes
# local edits take effect without a rebuild.
COPY --chown=airflow:root core/ /opt/airflow/core/
COPY --chown=airflow:root extractors/ /opt/airflow/extractors/
COPY --chown=airflow:root loaders/ /opt/airflow/loaders/
COPY --chown=airflow:root exporters/ /opt/airflow/exporters/
COPY --chown=airflow:root dags/ /opt/airflow/dags/
COPY --chown=airflow:root dbt/ /opt/airflow/dbt/
COPY --chown=airflow:root cfg/ /opt/airflow/cfg/

# The project packages live at /opt/airflow rather than being pip-installed, so
# that directory must be importable: Airflow only adds dags/, plugins/, and
# config/ to sys.path by itself.
ENV PYTHONPATH=/opt/airflow \
    DE_PROJECT_ROOT=/opt/airflow
