from pathlib import Path

from aioffice.application import CaseFactory, format_case_reference
from aioffice.application.services import DocumentImportService
from aioffice.infrastructure import FilesystemStorage, SQLiteCaseNumberProvider, SQLiteCaseRepository


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

    import sqlite3

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


def test_document_import_assigns_unique_reference_numbers(tmp_path: Path) -> None:
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
    first_source = tmp_path / "first.pdf"
    second_source = tmp_path / "second.pdf"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")

    service.import_pdf(first_source)
    service.import_pdf(second_source)

    persisted_cases = repository.list()

    assert tuple(case.reference_number for case in persisted_cases) == (1, 2)
    provider.close()
    repository.close()
