from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from exporters.cli import export_all, export_destination


@pytest.fixture
def marts_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS marts"))
        conn.execute(text("CREATE TABLE marts.example_items (item_id TEXT)"))
        conn.execute(text("INSERT INTO marts.example_items VALUES ('1')"))
    return engine


def test_destination_prefers_the_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_DATA_RAW_DIR", str(tmp_path))

    assert export_destination({"exports": {"destination": "data/exports"}}) == tmp_path


def test_destination_falls_back_to_config(monkeypatch):
    monkeypatch.delenv("DS_DATA_RAW_DIR", raising=False)

    destination = export_destination({"exports": {"destination": "data/exports"}})

    assert destination.is_absolute()
    assert destination.name == "exports"


def test_destination_defaults_when_unconfigured(monkeypatch):
    monkeypatch.delenv("DS_DATA_RAW_DIR", raising=False)

    assert export_destination({}).name == "exports"


def test_exports_every_configured_dataset(tmp_path, monkeypatch, marts_engine):
    monkeypatch.setenv("DS_DATA_RAW_DIR", str(tmp_path))
    config = {
        "exports": {
            "format": "csv",
            "datasets": [{"relation": "marts.example_items", "file_name": "items.csv"}],
        }
    }

    written = export_all(config, engine=marts_engine)

    assert written == [tmp_path / "items.csv"]
    assert written[0].exists()


def test_returns_nothing_when_no_datasets_are_configured(monkeypatch):
    monkeypatch.delenv("DS_DATA_RAW_DIR", raising=False)

    assert export_all({"exports": {"datasets": []}}) == []


def test_returns_nothing_when_exports_are_absent_entirely():
    assert export_all({}) == []


def test_shipped_config_declares_a_dataset_pointing_at_a_mart():
    """The configured export must name a relation the dbt project builds.

    cfg/config.yaml and dbt/models/ are edited independently; this fails the
    build if the export is left pointing at a mart that no longer exists.
    """
    from core.config import read_config, resolve_project_path

    datasets = read_config()["exports"]["datasets"]
    assert datasets, "the template should ship one worked example"

    marts_dir = Path(resolve_project_path("dbt/models/marts"))
    built_marts = {path.stem for path in marts_dir.glob("*.sql")}

    for dataset in datasets:
        table = dataset["relation"].split(".")[-1]
        assert table in built_marts, (
            f"cfg/config.yaml exports {dataset['relation']!r} but there is no "
            f"dbt model building it. Models present: {sorted(built_marts)}"
        )
