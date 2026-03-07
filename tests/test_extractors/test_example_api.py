import pytest

from extractors.api.example_api import ExampleApiExtractor


@pytest.fixture
def extractor(monkeypatch):
    monkeypatch.setenv("EXAMPLE_API_KEY", "test-key")
    return ExampleApiExtractor()


def test_extract_returns_records(extractor, httpx_mock):
    httpx_mock.add_response(
        url="https://api.example.com/v1/items",
        json=[{"id": "1", "value": "foo"}, {"id": "2", "value": "bar"}],
    )

    records = extractor.extract()

    assert len(records) == 2
    assert records[0] == {"id": "1", "value": "foo"}


def test_extract_returns_empty_list(extractor, httpx_mock):
    httpx_mock.add_response(
        url="https://api.example.com/v1/items",
        json=[],
    )

    records = extractor.extract()

    assert records == []


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("EXAMPLE_API_KEY", raising=False)
    with pytest.raises(KeyError):
        ExampleApiExtractor()
