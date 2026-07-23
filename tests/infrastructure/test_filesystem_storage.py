from hashlib import sha256
from pathlib import Path

import pytest

from aioffice.domain import StorageReference
from aioffice.application.storage import ArtifactNotFoundError, UnsupportedStorageError
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


def test_open_artifact_reads_existing_file(tmp_path: Path) -> None:
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    storage = FilesystemStorage(root_directory=tmp_path)
    reference = storage.store_file(source_path)

    with storage.open_artifact(reference) as handle:
        content = handle.read()

    assert content == b"contract-data"


def test_get_artifact_size_returns_size_without_exposing_path(tmp_path: Path) -> None:
    source_path = tmp_path / "offer.pdf"
    source_path.write_bytes(b"contract-data")
    storage = FilesystemStorage(root_directory=tmp_path)
    reference = storage.store_file(source_path)

    assert storage.get_artifact_size(reference) == len(b"contract-data")


def test_open_artifact_raises_controlled_error_for_missing_file(tmp_path: Path) -> None:
    storage = FilesystemStorage(root_directory=tmp_path)

    with pytest.raises(ArtifactNotFoundError, match="artifact file does not exist"):
        storage.open_artifact(
            StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/missing.pdf")
        )


def test_open_artifact_rejects_unsupported_storage_provider(tmp_path: Path) -> None:
    storage = FilesystemStorage(root_directory=tmp_path)

    with pytest.raises(UnsupportedStorageError, match="storage provider is not supported"):
        storage.open_artifact(StorageReference(storage_name="memory", locator="artifact.pdf"))


def test_open_artifact_rejects_parent_directory_locator(tmp_path: Path) -> None:
    storage = FilesystemStorage(root_directory=tmp_path)

    with pytest.raises(ArtifactNotFoundError, match="artifact locator is invalid"):
        storage.open_artifact(StorageReference(storage_name="filesystem", locator="../secret.txt"))


def test_open_artifact_rejects_absolute_locator(tmp_path: Path) -> None:
    storage = FilesystemStorage(root_directory=tmp_path)
    absolute_locator = str((tmp_path / "secret.txt").resolve())

    with pytest.raises(ArtifactNotFoundError, match="artifact locator is invalid"):
        storage.open_artifact(StorageReference(storage_name="filesystem", locator=absolute_locator))


def test_open_artifact_rejects_symlink_escape_without_leaking_root_path(tmp_path: Path) -> None:
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlink support is not available")

    storage = FilesystemStorage(root_directory=tmp_path)
    outside_file = tmp_path.parent / "outside-secret.txt"
    outside_file.write_text("secret")
    escaped_link = tmp_path / "artifacts" / "aa" / "bb" / "escaped.txt"
    escaped_link.parent.mkdir(parents=True, exist_ok=True)
    try:
        escaped_link.symlink_to(outside_file)
    except OSError:
        pytest.skip("symlinks are not available in this environment")

    with pytest.raises(ArtifactNotFoundError) as error:
        storage.open_artifact(
            StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/escaped.txt")
        )

    assert str(tmp_path) not in str(error.value)
