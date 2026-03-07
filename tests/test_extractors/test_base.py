import pytest

from extractors.base import BaseExtractor


def test_base_extractor_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseExtractor()  # type: ignore[abstract]


def test_concrete_subclass_must_implement_extract():
    class IncompleteExtractor(BaseExtractor):
        pass

    with pytest.raises(TypeError):
        IncompleteExtractor()  # type: ignore[abstract]


def test_concrete_subclass_works_when_extract_is_implemented():
    class StubExtractor(BaseExtractor):
        def extract(self):
            return [{"id": 1, "name": "test"}]

    extractor = StubExtractor()
    records = extractor.extract()
    assert records == [{"id": 1, "name": "test"}]
