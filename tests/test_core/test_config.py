from pathlib import Path

import pytest

from core.config import (
    dbt_paths,
    project_name,
    read_config,
    resolve_project_path,
    warehouse_schemas,
)


def test_read_config_loads_the_tracked_file():
    config = read_config()

    assert "warehouse" in config
    assert "exports" in config


def test_project_name_matches_pyproject():
    assert project_name() == "de-template"


def test_resolve_project_path_leaves_absolute_paths_alone():
    absolute = Path("/tmp/somewhere")

    assert resolve_project_path(absolute) == absolute


def test_resolve_project_path_anchors_relative_paths_at_the_root():
    resolved = resolve_project_path("cfg/config.yaml")

    assert resolved.is_absolute()
    assert resolved.exists()


def test_warehouse_schemas_reads_configured_values():
    schemas = warehouse_schemas({"warehouse": {"marts_schema": "analytics"}})

    assert schemas["marts"] == "analytics"
    # Unconfigured layers still get their defaults.
    assert schemas["raw"] == "raw"
    assert schemas["staging"] == "staging"


def test_warehouse_schemas_defaults_when_unconfigured():
    assert warehouse_schemas({}) == {
        "raw": "raw",
        "staging": "staging",
        "marts": "marts",
    }


def test_dbt_paths_are_absolute_locally():
    paths = dbt_paths(read_config())

    assert Path(paths["project_dir"]).is_absolute()
    assert Path(paths["profiles_dir"]).is_absolute()


def test_dbt_paths_use_the_mount_point_in_a_container():
    paths = dbt_paths(read_config(), in_container=True)

    assert paths == {
        "project_dir": "/opt/airflow/dbt",
        "profiles_dir": "/opt/airflow/dbt",
    }


def test_configured_schemas_match_the_dbt_project():
    """The dbt models must land in the schemas the rest of the project expects.

    These are configured in two files that cannot see each other, so a rename
    in one silently breaks the other. This catches it.
    """
    import yaml

    schemas = warehouse_schemas(read_config())
    dbt_project = yaml.safe_load(
        (resolve_project_path("dbt/dbt_project.yml")).read_text(encoding="utf-8")
    )
    models = dbt_project["models"]["de_template"]

    assert models["staging"]["+schema"] == schemas["staging"]
    assert models["marts"]["+schema"] == schemas["marts"]


@pytest.mark.parametrize("source_name", ["example_items"])
def test_configured_sources_declare_an_extractor_and_a_target(source_name):
    source = read_config()["sources"][source_name]

    assert ":" in source["extractor"]
    assert "." in source["target_table"]
