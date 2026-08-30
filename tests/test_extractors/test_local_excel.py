import io

import pytest
from openpyxl import Workbook

from core.local_files import LocalFolderClient
from extractors.files.local_excel import (
    LocalCustomersExtractor,
    LocalLatestOrdersExtractor,
    LocalSeedExtractor,
)


def _workbook_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path):
    return LocalFolderClient(base_dir=tmp_path)


def test_extract_reads_rows_from_local_disk(client):
    content = _workbook_bytes([["order_id", "amount"], ["1", 10.5]])
    client.upload_file("Sample Data", "latest_orders.xlsx", content)
    extractor = LocalLatestOrdersExtractor(client=client)

    records = extractor.extract()

    assert records == [
        {
            "order_id": "1",
            "amount": 10.5,
            "_source_file": "latest_orders.xlsx",
            "_source_modified": records[0]["_source_modified"],
        }
    ]
    assert records[0]["_source_modified"] is not None


def test_extractor_only_reads_its_own_kind(client):
    client.upload_file(
        "Sample Data", "seed_categories.xlsx", _workbook_bytes([["a"], [1]])
    )
    client.upload_file("Sample Data", "customers.xlsx", _workbook_bytes([["a"], [2]]))
    extractor = LocalSeedExtractor(client=client)

    records = extractor.extract()

    assert {r["_source_file"] for r in records} == {"seed_categories.xlsx"}


def test_constructor_defaults_client_and_folder_from_config(monkeypatch, tmp_path):
    monkeypatch.setattr("core.local_files.read_config", lambda: {})
    monkeypatch.setattr(
        "core.local_files.resolve_project_path", lambda path: tmp_path / path
    )

    extractor = LocalCustomersExtractor()

    assert isinstance(extractor.client, LocalFolderClient)
    assert extractor.folder_path == "Sample Data"
