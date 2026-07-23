from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from aioffice.application import (
    ArtifactLocatorConflictError,
    CaseFactory,
    CaseRepository,
    PersistedCase,
    format_case_reference,
)
from aioffice.application.services import DocumentImportService
from aioffice.domain import Artifact, ArtifactType, Case, Identifier
from aioffice.infrastructure import FilesystemStorage, SQLiteCaseNumberProvider, SQLiteCaseRepository


@dataclass(slots=True)
class _CountingNumberProvider:
    next_value: int = 1
    calls: int = 0

    def next_number(self) -> int:
        value = self.next_value
        self.next_value += 1
        self.calls += 1
        return value


@dataclass(slots=True)
class _RaceConditionRepository(CaseRepository):
    persisted_case: PersistedCase
    save_calls: int = 0
    get_calls: int = 0

    def save(self, case: Case, reference_number: int) -> None:
        self.save_calls += 1
        raise ArtifactLocatorConflictError("artifact locator is already assigned to another case")

    def get(self, case_id: Identifier) -> PersistedCase | None:
        if self.persisted_case.case.id == case_id:
            return self.persisted_case
        return None

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        self.get_calls += 1
        if self.get_calls == 1:
            return None
        return self.persisted_case

    def list(self) -> tuple[PersistedCase, ...]:
        return (self.persisted_case,)

    def count(self) -> int:
        return 1


@dataclass(slots=True)
class _IntegrityErrorRepository(CaseRepository):
    error_message: str
    save_calls: int = 0

    def save(self, case: Case, reference_number: int) -> None:
        self.save_calls += 1
        raise sqlite3.IntegrityError(self.error_message)

    def get(self, case_id: Identifier) -> PersistedCase | None:
        return None

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        return None

    def list(self) -> tuple[PersistedCase, ...]:
        return ()

    def count(self) -> int:
        return 0


def _service(tmp_path: Path) -> tuple[DocumentImportService, SQLiteCaseRepository, SQLiteCaseNumberProvider]:
    database_path = tmp_path / "storage" / "aioffice.db"
    storage = FilesystemStorage(root_directory=tmp_path)
    repository = SQLiteCaseRepository(database_path=database_path)
    provider = SQLiteCaseNumberProvider(database_path=database_path)
    service = DocumentImportService(
        storage=storage,
        case_factory=CaseFactory(),
        case_repository=repository,
        case_number_provider=provider,
    )
    return service, repository, provider


def test_format_case_reference_formats_numbers_for_users() -> None:
    assert format_case_reference(1) == "CASE-000001"
    assert format_case_reference(17) == "CASE-000017"
    assert format_case_reference(205) == "CASE-000205"


def test_sqlite_case_number_provider_allocates_sequential_numbers(tmp_path: Path) -> None:
    provider = SQLiteCaseNumberProvider(database_path=tmp_path / "storage" / "aioffice.db")

    first_number = provider.next_number()
    second_number = provider.next_number()

    assert (first_number, second_number) == (1, 2)
    provider.close()


def test_sqlite_case_number_provider_preserves_sequence_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    first_provider = SQLiteCaseNumberProvider(database_path=database_path)
    assert first_provider.next_number() == 1
    first_provider.close()

    second_provider = SQLiteCaseNumberProvider(database_path=database_path)

    assert second_provider.next_number() == 2
    second_provider.close()


def test_sqlite_case_number_provider_migration_uses_next_free_number(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    repository = SQLiteCaseRepository(database_path=database_path)
    repository.close()

    connection = sqlite3.connect(database_path)
    connection.execute("DROP TABLE cases")
    connection.execute(
        """
        CREATE TABLE cases (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO cases (id, status, created_at) VALUES (?, ?, ?)",
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "open", "2026-07-22T12:00:00+00:00"),
    )
    connection.execute(
        "INSERT INTO cases (id, status, created_at) VALUES (?, ?, ?)",
        ("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "open", "2026-07-22T12:01:00+00:00"),
    )
    connection.execute(
        "INSERT INTO cases (id, status, created_at) VALUES (?, ?, ?)",
        ("cccccccc-cccc-cccc-cccc-cccccccccccc", "open", "2026-07-22T12:02:00+00:00"),
    )
    connection.commit()
    connection.close()

    migrated_repository = SQLiteCaseRepository(database_path=database_path)
    migrated_repository.close()
    provider = SQLiteCaseNumberProvider(database_path=database_path)

    assert provider.next_number() == 4
    provider.close()


def test_first_import_creates_case(tmp_path: Path) -> None:
    service, repository, provider = _service(tmp_path)
    source = tmp_path / "offer.pdf"
    source.write_bytes(b"offer")

    created_case = service.import_pdf(source)

    assert created_case is not None
    assert repository.count() == 1
    provider.close()
    repository.close()


def test_second_import_of_identical_content_returns_same_case(tmp_path: Path) -> None:
    service, repository, provider = _service(tmp_path)
    first_source = tmp_path / "offer.pdf"
    second_source = tmp_path / "copy-of-offer.pdf"
    first_source.write_bytes(b"offer")
    second_source.write_bytes(b"offer")

    first_case = service.import_pdf(first_source)
    second_case = service.import_pdf(second_source)

    assert first_case is not None
    assert second_case is not None
    assert second_case.id == first_case.id
    assert repository.count() == 1
    provider.close()
    repository.close()


def test_duplicate_import_does_not_call_next_number_again(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    storage = FilesystemStorage(root_directory=tmp_path)
    repository = SQLiteCaseRepository(database_path=database_path)
    provider = _CountingNumberProvider()
    service = DocumentImportService(
        storage=storage,
        case_factory=CaseFactory(),
        case_repository=repository,
        case_number_provider=provider,
    )
    first_source = tmp_path / "offer.pdf"
    second_source = tmp_path / "copy-of-offer.pdf"
    first_source.write_bytes(b"offer")
    second_source.write_bytes(b"offer")

    service.import_pdf(first_source)
    service.import_pdf(second_source)

    assert provider.calls == 1
    repository.close()


def test_import_of_different_content_creates_new_case(tmp_path: Path) -> None:
    service, repository, provider = _service(tmp_path)
    first_source = tmp_path / "first.pdf"
    second_source = tmp_path / "second.pdf"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")

    first_case = service.import_pdf(first_source)
    second_case = service.import_pdf(second_source)

    assert first_case is not None
    assert second_case is not None
    assert first_case.id != second_case.id
    assert tuple(case.reference_number for case in repository.list()) == (1, 2)
    provider.close()
    repository.close()


def test_concurrent_unique_locator_conflict_returns_existing_case(tmp_path: Path) -> None:
    storage = FilesystemStorage(root_directory=tmp_path)
    existing_source = tmp_path / "existing.pdf"
    existing_source.write_bytes(b"conflict")
    stored_reference = storage.store_file(existing_source)
    existing_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    existing_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=stored_reference,
        )
    )
    persisted_case = PersistedCase(
        case=existing_case,
        reference_number=1,
        status="open",
        created_at="2026-07-23T10:00:00+00:00",
    )
    repository = _RaceConditionRepository(persisted_case=persisted_case)
    provider = _CountingNumberProvider()
    service = DocumentImportService(
        storage=storage,
        case_factory=CaseFactory(),
        case_repository=repository,
        case_number_provider=provider,
    )
    source = tmp_path / "offer.pdf"
    source.write_bytes(b"conflict")

    returned_case = service.import_pdf(source)

    assert returned_case is not None
    assert returned_case.id == existing_case.id
    assert provider.calls == 1
    assert repository.save_calls == 1
    assert repository.get_calls == 2


def test_other_integrity_errors_are_not_hidden(tmp_path: Path) -> None:
    storage = FilesystemStorage(root_directory=tmp_path)
    repository = _IntegrityErrorRepository(error_message="UNIQUE constraint failed: cases.reference_number")
    provider = _CountingNumberProvider()
    service = DocumentImportService(
        storage=storage,
        case_factory=CaseFactory(),
        case_repository=repository,
        case_number_provider=provider,
    )
    source = tmp_path / "offer.pdf"
    source.write_bytes(b"offer")

    with pytest.raises(sqlite3.IntegrityError, match="cases.reference_number"):
        service.import_pdf(source)
