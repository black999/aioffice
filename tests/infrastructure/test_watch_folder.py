from pathlib import Path

from aioffice.application import CaseFactory, InMemoryCaseRegistry
from aioffice.infrastructure import FilesystemStorage, WatchFolder


def test_new_pdf_creates_one_case(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "offer.pdf"
    source_path.write_bytes(b"offer")
    registry = InMemoryCaseRegistry()
    watch_folder = WatchFolder(
        watch_directory=watch_directory,
        storage=FilesystemStorage(root_directory=tmp_path),
        case_factory=CaseFactory(),
        registry=registry,
    )

    case = watch_folder.process_path(source_path)

    assert case is not None
    assert registry.count() == 1
    assert case.artifacts[0].artifact_type.value == "pdf"


def test_duplicate_pdf_creates_no_second_case(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    first_pdf = watch_directory / "offer.pdf"
    second_pdf = watch_directory / "renamed.pdf"
    first_pdf.write_bytes(b"same-content")
    second_pdf.write_bytes(b"same-content")
    registry = InMemoryCaseRegistry()
    watch_folder = WatchFolder(
        watch_directory=watch_directory,
        storage=FilesystemStorage(root_directory=tmp_path),
        case_factory=CaseFactory(),
        registry=registry,
    )

    first_case = watch_folder.process_path(first_pdf)
    second_case = watch_folder.process_path(second_pdf)

    assert first_case is not None
    assert second_case is None
    assert registry.count() == 1


def test_non_pdf_is_ignored(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "offer.txt"
    source_path.write_bytes(b"offer")
    registry = InMemoryCaseRegistry()
    watch_folder = WatchFolder(
        watch_directory=watch_directory,
        storage=FilesystemStorage(root_directory=tmp_path),
        case_factory=CaseFactory(),
        registry=registry,
    )

    case = watch_folder.process_path(source_path)

    assert case is None
    assert registry.count() == 0


def test_temporary_pdf_is_ignored(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "~$offer.pdf"
    source_path.write_bytes(b"offer")
    registry = InMemoryCaseRegistry()
    watch_folder = WatchFolder(
        watch_directory=watch_directory,
        storage=FilesystemStorage(root_directory=tmp_path),
        case_factory=CaseFactory(),
        registry=registry,
    )

    case = watch_folder.process_path(source_path)

    assert case is None
    assert registry.count() == 0
