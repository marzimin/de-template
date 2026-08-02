import pytest

from core.imports import import_from_path
from extractors.base import BaseExtractor


def test_imports_a_class_by_path():
    imported = import_from_path("extractors.base:BaseExtractor")

    assert imported is BaseExtractor


def test_configured_extractor_resolves_to_a_real_extractor():
    """The extractor named in cfg/config.yaml must actually be importable.

    Without this, a typo there surfaces as a failed Airflow task rather than a
    failed build.
    """
    from core.config import read_config

    for source in read_config()["sources"].values():
        extractor_class = import_from_path(source["extractor"])
        assert issubclass(extractor_class, BaseExtractor)


@pytest.mark.parametrize(
    "path",
    ["extractors.base", "", ":BaseExtractor", "extractors.base:"],
)
def test_rejects_paths_that_are_not_module_colon_attribute(path):
    with pytest.raises(ValueError, match="Invalid import path"):
        import_from_path(path)


def test_raises_import_error_for_a_missing_attribute():
    with pytest.raises(ImportError, match="has no attribute"):
        import_from_path("extractors.base:NoSuchClass")


def test_raises_import_error_for_a_missing_module():
    with pytest.raises(ImportError):
        import_from_path("extractors.nope:Thing")
