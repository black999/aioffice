from hashlib import sha256
from pathlib import Path

import pytest

from aioffice.domain import StorageReference
from aioffice.infrastructure import AppSettings
from aioffice.infrastructure.storage import FilesystemStorage


def test_store_file_stores_new_file_and_returns_reference(tmp_path: Path) -> None:
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    storage = FilesystemStorage(root_directory=tmp_path)

    reference = storage.store_file(source_path)

    expected_hash = sha256(b"contract-data").hexdigest()
    expected_locator = f"artifacts/{expected_hash[:2]}/{expected_hash[2:4]}/{expected_hash}.pdf"
    stored_path = tmp_path / Path(reference.locator)

    assert reference == StorageReference(storage_name="filesystem", locator=expected_locator)
    assert stored_path.read_bytes() == b"contract-data"
    assert not reference.locator.startswith(str(tmp_path))


def test_store_file_returns_existing_reference_for_duplicate_content(tmp_path: Path) -> None:
    first_source = tmp_path / "offer.pdf"
    second_source = tmp_path / "renamed.txt"
    first_source.write_bytes(b"same-content")
    second_source.write_bytes(b"same-content")
    storage = FilesystemStorage(root_directory=tmp_path)

    first_reference = storage.store_file(first_source)
    second_reference = storage.store_file(second_source)

    stored_files = list((tmp_path / "artifacts").rglob("*"))

    assert first_reference == second_reference
    assert sorted(path for path in stored_files if path.is_file()) == [
        tmp_path / Path(first_reference.locator)
    ]


def test_calculate_sha256_matches_known_hash(tmp_path: Path) -> None:
    source_path = tmp_path / "input.bin"
    source_path.write_bytes(b"abc123")
    storage = FilesystemStorage(root_directory=tmp_path)

    result = storage.calculate_sha256(source_path)

    assert result == sha256(b"abc123").hexdigest()


def test_store_file_creates_nested_directory_structure(tmp_path: Path) -> None:
    source_path = tmp_path / "message.eml"
    source_path.write_bytes(b"mail")
    storage = FilesystemStorage(root_directory=tmp_path)

    reference = storage.store_file(source_path)
    stored_path = tmp_path / Path(reference.locator)

    assert stored_path.parent.parent.parent.name == "artifacts"
    assert stored_path.parent.exists()
    assert stored_path.exists()


def test_store_file_uses_root_directory_artifacts_path(tmp_path: Path) -> None:
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    storage = FilesystemStorage(root_directory=tmp_path)

    reference = storage.store_file(source_path)

    assert (tmp_path / Path(reference.locator)).exists()
    assert (tmp_path / "artifacts").exists()


def test_store_file_does_not_create_nested_storage_directory(tmp_path: Path) -> None:
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    storage = FilesystemStorage(root_directory=tmp_path)

    storage.store_file(source_path)

    assert not (tmp_path / "storage").exists()


def test_store_file_uses_root_directory_staging(tmp_path: Path) -> None:
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    storage = FilesystemStorage(root_directory=tmp_path)

    storage.store_file(source_path)

    assert (tmp_path / ".staging").exists()


def test_store_file_locator_keeps_expected_relative_format(tmp_path: Path) -> None:
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    storage = FilesystemStorage(root_directory=tmp_path)

    reference = storage.store_file(source_path)

    assert reference.locator.count("/") == 3
    assert reference.locator.startswith("artifacts/")
    assert reference.locator.endswith(".pdf")


def test_storage_finds_existing_artifact_after_recreation(tmp_path: Path) -> None:
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    first_storage = FilesystemStorage(root_directory=tmp_path)
    first_reference = first_storage.store_file(source_path)

    recreated_storage = FilesystemStorage(root_directory=tmp_path)
    second_reference = recreated_storage.store_file(source_path)

    assert second_reference == first_reference


def test_storage_works_with_settings_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOFFICE_DATA_DIR", str(tmp_path / "aioffice-data"))
    settings = AppSettings.from_environment()
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    storage = FilesystemStorage(root_directory=settings.data_directory)

    reference = storage.store_file(source_path)

    assert (settings.data_directory / Path(reference.locator)).exists()
    assert settings.artifacts_directory == settings.data_directory / "artifacts"
