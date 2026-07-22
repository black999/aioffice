from pathlib import Path

from aioffice.application import CaseFactory
from aioffice.application.services import DocumentImportService
from aioffice.infrastructure import (
    FilesystemStorage,
    SQLiteCaseNumberProvider,
    SQLiteCaseRepository,
    WatchFolder,
)


def _build_watch_folder(tmp_path: Path, watch_directory: Path) -> tuple[WatchFolder, SQLiteCaseRepository, SQLiteCaseNumberProvider]:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseRepository(database_path=database_path)
    number_provider = SQLiteCaseNumberProvider(database_path=database_path)
    import_service = DocumentImportService(
        storage=FilesystemStorage(root_directory=tmp_path),
        case_factory=CaseFactory(),
        case_repository=repository,
        case_number_provider=number_provider,
    )
    watch_folder = WatchFolder(
        watch_directory=watch_directory,
        import_service=import_service,
    )
    return watch_folder, repository, number_provider


def test_new_pdf_creates_one_case(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "offer.pdf"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    case = watch_folder.process_path(source_path)

    assert case is not None
    assert repository.count() == 1
    assert case.artifacts[0].artifact_type.value == "pdf"
    number_provider.close()
    repository.close()


def test_duplicate_pdf_creates_no_second_case(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    first_pdf = watch_directory / "offer.pdf"
    second_pdf = watch_directory / "renamed.pdf"
    first_pdf.write_bytes(b"same-content")
    second_pdf.write_bytes(b"same-content")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    first_case = watch_folder.process_path(first_pdf)
    second_case = watch_folder.process_path(second_pdf)

    assert first_case is not None
    assert second_case is None
    assert repository.count() == 1
    number_provider.close()
    repository.close()


def test_non_pdf_is_ignored(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "offer.txt"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    case = watch_folder.process_path(source_path)

    assert case is None
    assert repository.count() == 0
    number_provider.close()
    repository.close()


def test_temporary_pdf_is_ignored(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "~$offer.pdf"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    case = watch_folder.process_path(source_path)

    assert case is None
    assert repository.count() == 0
    number_provider.close()
    repository.close()
