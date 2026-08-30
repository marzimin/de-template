import pytest

from core.local_files import DEFAULT_DESTINATION, LocalFolderClient, default_folder_path


@pytest.fixture
def client(tmp_path):
    return LocalFolderClient(base_dir=tmp_path)


def test_list_children_empty_folder_returns_empty_list(client):
    assert client.list_children("Sample Data") == []


def test_upload_then_list_then_download_round_trips(client):
    written = client.upload_file("Sample Data", "orders.xlsx", b"workbook-bytes")

    assert written["name"] == "orders.xlsx"
    assert written["id"] == "Sample Data/orders.xlsx"

    items = client.list_children("Sample Data")
    assert len(items) == 1
    assert items[0]["name"] == "orders.xlsx"
    assert "file" in items[0]
    assert "lastModifiedDateTime" in items[0]

    assert client.download(items[0]["id"]) == b"workbook-bytes"


def test_upload_overwrites_existing_file(client):
    client.upload_file("Sample Data", "orders.xlsx", b"first")
    client.upload_file("Sample Data", "orders.xlsx", b"second")

    items = client.list_children("Sample Data")
    assert len(items) == 1
    assert client.download(items[0]["id"]) == b"second"


def test_list_children_marks_subfolders(client):
    (client._base_dir / "Sample Data" / "Nested").mkdir(parents=True)
    client.upload_file("Sample Data", "orders.xlsx", b"content")

    items = {item["name"]: item for item in client.list_children("Sample Data")}

    assert "file" in items["orders.xlsx"]
    assert "folder" in items["Nested"]


def test_list_children_strips_slashes(client):
    client.upload_file("Sample Data", "orders.xlsx", b"content")

    assert len(client.list_children("/Sample Data/")) == 1


def test_from_config_uses_default_destination(monkeypatch, tmp_path):
    monkeypatch.setattr("core.local_files.read_config", lambda: {})
    monkeypatch.setattr(
        "core.local_files.resolve_project_path", lambda path: tmp_path / path
    )

    client = LocalFolderClient.from_config()

    assert client._base_dir == tmp_path / DEFAULT_DESTINATION


def test_default_folder_path_reads_config(monkeypatch):
    monkeypatch.setattr(
        "core.local_files.read_config",
        lambda: {"local_dummy_data": {"folder_path": "Custom Folder"}},
    )

    assert default_folder_path() == "Custom Folder"
