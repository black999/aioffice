from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import pytest

from aioffice.application import CaseFactory
from aioffice.application.services import DocumentImportService
from aioffice.domain import Case
from watchdog.observers.api import BaseObserver
from aioffice.infrastructure import (
    FilesystemStorage,
    SQLiteCaseNumberProvider,
    SQLiteCaseRepository,
    WatchFolder,
)


class _FakeObserver:
    def __init__(self) -> None:
        self.scheduled: list[tuple[object, str, bool]] = []
        self.started = False
        self.stopped = False
        self.joined = False

    def schedule(self, event_handler: object, path: str, recursive: bool) -> None:
        self.scheduled.append((event_handler, path, recursive))

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def is_alive(self) -> bool:
        return self.started and not self.stopped

    def join(self) -> None:
        self.joined = True


def _build_watch_folder(
    tmp_path: Path, watch_directory: Path
) -> tuple[WatchFolder, SQLiteCaseRepository, SQLiteCaseNumberProvider]:
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
        processed_directory=tmp_path / "processed",
        import_service=import_service,
    )
    watch_folder._observer = cast(BaseObserver, _FakeObserver())
    return watch_folder, repository, number_provider


def test_start_creates_incoming_and_processed_directories(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    watch_folder.start()

    assert watch_directory.exists()
    assert (tmp_path / "processed").exists()
    number_provider.close()
    repository.close()


def test_existing_pdf_is_imported_during_startup(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "offer.pdf"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    watch_folder.start()

    assert repository.count() == 1
    assert not source_path.exists()
    assert (tmp_path / "processed" / "offer.pdf").exists()
    number_provider.close()
    repository.close()


def test_existing_pdfs_are_processed_in_stable_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    for name in ("b.pdf", "a.pdf", "c.pdf"):
        (watch_directory / name).write_bytes(name.encode())
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)
    processed: list[str] = []
    original_process_path = WatchFolder.process_path

    def process_path(self: WatchFolder, file_path: Path) -> Case | None:
        processed.append(file_path.name)
        return original_process_path(self, file_path)

    monkeypatch.setattr(WatchFolder, "process_path", process_path)

    watch_folder.start()

    assert processed == ["a.pdf", "b.pdf", "c.pdf"]
    number_provider.close()
    repository.close()


def test_existing_non_pdf_is_ignored_during_startup(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    (watch_directory / "offer.txt").write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    watch_folder.start()

    assert repository.count() == 0
    assert (watch_directory / "offer.txt").exists()
    number_provider.close()
    repository.close()


def test_existing_subdirectory_is_ignored_during_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    (watch_directory / "subdir").mkdir()
    (watch_directory / "subdir" / "offer.pdf").write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)
    processed: list[str] = []
    original_process_path = WatchFolder.process_path

    def process_path(self: WatchFolder, file_path: Path) -> Case | None:
        processed.append(file_path.name)
        return original_process_path(self, file_path)

    monkeypatch.setattr(WatchFolder, "process_path", process_path)

    watch_folder.start()

    assert processed == []
    assert repository.count() == 0
    number_provider.close()
    repository.close()


def test_error_in_one_existing_pdf_does_not_block_next_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    broken_path = watch_directory / "a.pdf"
    good_path = watch_directory / "b.pdf"
    broken_path.write_bytes(b"broken")
    good_path.write_bytes(b"good")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)
    original_process_path = WatchFolder.process_path

    def process_path(self: WatchFolder, file_path: Path) -> Case | None:
        if file_path == broken_path:
            raise RuntimeError("boom")
        return original_process_path(self, file_path)

    monkeypatch.setattr(WatchFolder, "process_path", process_path)

    watch_folder.start()

    assert repository.count() == 1
    assert broken_path.exists()
    assert not good_path.exists()
    assert (tmp_path / "processed" / "b.pdf").exists()
    number_provider.close()
    repository.close()


def test_process_path_moves_file_to_processed_and_returns_case(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "offer.pdf"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    case = watch_folder.process_path(source_path)

    assert case is not None
    assert repository.count() == 1
    assert not source_path.exists()
    assert (tmp_path / "processed" / "offer.pdf").exists()
    number_provider.close()
    repository.close()


def test_duplicate_pdf_creates_no_second_case_and_moves_source_file(tmp_path: Path) -> None:
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
    assert not second_pdf.exists()
    assert (tmp_path / "processed" / "renamed.pdf").exists()
    number_provider.close()
    repository.close()


def test_import_error_leaves_file_in_incoming(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "offer.pdf"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    def import_pdf(self: DocumentImportService, source_path: Path) -> Case | None:
        raise RuntimeError("boom")

    monkeypatch.setattr(DocumentImportService, "import_pdf", import_pdf)

    with pytest.raises(RuntimeError, match="boom"):
        watch_folder.process_path(source_path)

    assert source_path.exists()
    assert not (tmp_path / "processed" / "offer.pdf").exists()
    number_provider.close()
    repository.close()


def test_processed_name_conflict_uses_incrementing_suffixes(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    processed_directory = tmp_path / "processed"
    watch_directory.mkdir()
    processed_directory.mkdir()
    (processed_directory / "offer.pdf").write_bytes(b"first")
    (processed_directory / "offer-1.pdf").write_bytes(b"second")
    source_path = watch_directory / "offer.pdf"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    watch_folder.process_path(source_path)

    assert (processed_directory / "offer.pdf").read_bytes() == b"first"
    assert (processed_directory / "offer-1.pdf").read_bytes() == b"second"
    assert (processed_directory / "offer-2.pdf").exists()
    number_provider.close()
    repository.close()


def test_processed_name_conflict_preserves_extension(tmp_path: Path) -> None:
    watch_directory = tmp_path / "incoming"
    processed_directory = tmp_path / "processed"
    watch_directory.mkdir()
    processed_directory.mkdir()
    (processed_directory / "offer.final.pdf").write_bytes(b"first")
    source_path = watch_directory / "offer.final.pdf"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    watch_folder.process_path(source_path)

    assert (processed_directory / "offer.final-1.pdf").exists()
    number_provider.close()
    repository.close()


def test_move_error_leaves_file_in_incoming(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_directory = tmp_path / "incoming"
    watch_directory.mkdir()
    source_path = watch_directory / "offer.pdf"
    source_path.write_bytes(b"offer")
    watch_folder, repository, number_provider = _build_watch_folder(tmp_path, watch_directory)

    def move(_: str, __: str) -> str:
        raise OSError("move failed")

    monkeypatch.setattr(shutil, "move", move)

    with pytest.raises(OSError, match="move failed"):
        watch_folder.process_path(source_path)

    assert source_path.exists()
    assert repository.count() == 1
    number_provider.close()
    repository.close()
