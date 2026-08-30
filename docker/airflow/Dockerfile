# Override with --build-arg AIRFLOW_VERSION=x.y.z, or set AIRFLOW_VERSION in
# .env — docker-compose.yml passes it through automatically. Bumping this file
# is a one-line change; verify with `make build && make up && make test`
# before trusting a new version (Airflow 3.x has had real breaking changes
# between minors). Declared before FROM, so it is only in scope for that line
# — re-declared below where later steps need it for the image label.
ARG AIRFLOW_VERSION=3.3.1
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12

ARG AIRFLOW_VERSION
ARG VERSION=dev
LABEL org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.base.version="${AIRFLOW_VERSION}"

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# uv for the actual install below — the same tool that manages every other
# dependency in this project (pyproject.toml/uv.lock), and meaningfully
# faster than pip for a resolve this size. A static binary, copied in
# directly per Astral's documented pattern — no separate installer step or
# Python-side uv package.
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv

# Install dbt and the project's runtime dependencies inside the Airflow image.
# Kept in step with pyproject.toml by tests/test_requirements_sync.py.
# --python (not --system): the base image's site-packages is root-owned and
# this step runs as the unprivileged `airflow` user, so `--system` fails with
# a permission error. Pointing uv at the airflow user's own interpreter makes
# it resolve to /home/airflow/.local — the same user-writable location plain
# `pip install` falls back to here — without needing a venv. Verified against
# a real build; do not change back to --system without re-testing.
COPY --chown=airflow:root requirements-airflow.txt /opt/airflow/
RUN uv pip install --python "$(command -v python3)" --no-cache -r /opt/airflow/requirements-airflow.txt

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
