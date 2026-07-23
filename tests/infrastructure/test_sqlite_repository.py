import sqlite3
from pathlib import Path

import pytest

from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference
from aioffice.infrastructure import SQLiteCaseRepository


def test_save_case_persists_case(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        )
    )

    repository.save(case, reference_number=1)

    assert repository.count() == 1
    repository.close()


def test_load_case_returns_case_by_identifier(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    repository.save(Case(id=case_id), reference_number=1)

    loaded_case = repository.get(case_id)

    assert loaded_case is not None
    assert loaded_case.case.id == case_id
    assert loaded_case.case.artifacts == ()
    assert loaded_case.reference_number == 1
    repository.close()


def test_list_cases_returns_all_persisted_cases(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    repository.save(first_case, reference_number=1)
    repository.save(second_case, reference_number=2)

    cases = repository.list()

    assert tuple(case.case.id for case in cases) == (first_case.id, second_case.id)
    assert tuple(case.reference_number for case in cases) == (1, 2)
    repository.close()


def test_repository_persists_after_reopening(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    first_repository = SQLiteCaseRepository(database_path=database_path)
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    first_repository.save(Case(id=case_id), reference_number=1)
    first_repository.close()

    second_repository = SQLiteCaseRepository(database_path=database_path)

    assert second_repository.count() == 1
    loaded_case = second_repository.get(case_id)
    assert loaded_case is not None
    assert loaded_case.case.id == case_id
    assert loaded_case.reference_number == 1
    second_repository.close()


def test_empty_repository_returns_no_cases(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")

    assert repository.count() == 0
    assert repository.list() == ()
    assert repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")) is None
    repository.close()


def test_get_by_artifact_locator_returns_existing_case(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        )
    )
    repository.save(case, reference_number=1)

    loaded_case = repository.get_by_artifact_locator("artifacts/aa/bb/file.pdf")

    assert loaded_case is not None
    assert loaded_case.case.id == case.id
    repository.close()


def test_get_by_artifact_locator_returns_none_for_unknown_locator(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")

    assert repository.get_by_artifact_locator("artifacts/aa/bb/missing.pdf") is None
    repository.close()


def test_get_by_artifact_locator_ignores_cases_without_artifact(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    repository.save(Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")), reference_number=1)

    assert repository.get_by_artifact_locator("artifacts/aa/bb/file.pdf") is None
    repository.close()


def test_repository_creates_locator_indexes(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseRepository(database_path=database_path)
    repository.close()

    connection = sqlite3.connect(database_path)
    index_names = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    }
    connection.close()

    assert "ix_cases_primary_artifact_locator" in index_names
    assert "ux_cases_primary_artifact_locator" in index_names


def test_repository_rejects_duplicate_non_empty_locator(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    first_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        )
    )
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    second_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        )
    )
    repository.save(first_case, reference_number=1)

    with pytest.raises(sqlite3.IntegrityError):
        repository.save(second_case, reference_number=2)

    repository.close()


def test_repository_allows_multiple_cases_without_locator(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))

    repository.save(first_case, reference_number=1)
    repository.save(second_case, reference_number=2)

    assert repository.count() == 2
    repository.close()


def test_repository_migration_raises_for_existing_duplicate_locators(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE cases (
            id TEXT PRIMARY KEY,
            reference_number INTEGER UNIQUE NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            primary_artifact_locator TEXT
        )
        """
    )
    duplicate_locator = "artifacts/aa/bb/file.pdf"
    connection.execute(
        "INSERT INTO cases (id, reference_number, status, created_at, primary_artifact_locator) VALUES (?, ?, ?, ?, ?)",
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 1, "open", "2026-07-22T12:00:00+00:00", duplicate_locator),
    )
    connection.execute(
        "INSERT INTO cases (id, reference_number, status, created_at, primary_artifact_locator) VALUES (?, ?, ?, ?, ?)",
        ("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", 2, "open", "2026-07-22T12:01:00+00:00", duplicate_locator),
    )
    connection.commit()
    connection.close()

    try:
        SQLiteCaseRepository(database_path=database_path)
    except RuntimeError as error:
        assert "duplicate primary_artifact_locator values already exist" in str(error)
        assert duplicate_locator in str(error)
    else:
        msg = "expected RuntimeError for duplicate locator migration"
        raise AssertionError(msg)
