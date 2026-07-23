import sqlite3
from pathlib import Path

import pytest

from aioffice.application import ArtifactLocatorConflictError, ArtifactRecord
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
    assert loaded_case.case.artifacts[0].artifact_type is ArtifactType.PDF
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

    with pytest.raises(ArtifactLocatorConflictError):
        repository.save(second_case, reference_number=2)

    repository.close()


def test_pdf_artifact_keeps_pdf_type_after_reloading(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseRepository(database_path=database_path)
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    case = Case(id=case_id)
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        )
    )
    repository.save(case, reference_number=1)
    repository.close()

    reloaded_repository = SQLiteCaseRepository(database_path=database_path)
    loaded_case = reloaded_repository.get(case_id)

    assert loaded_case is not None
    assert loaded_case.case.artifacts[0].artifact_type is ArtifactType.PDF
    reloaded_repository.close()


def test_email_artifact_keeps_email_type_after_reloading(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseRepository(database_path=database_path)
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    case = Case(id=case_id)
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.eml"),
        )
    )
    repository.save(case, reference_number=1)
    repository.close()

    reloaded_repository = SQLiteCaseRepository(database_path=database_path)
    loaded_case = reloaded_repository.get(case_id)

    assert loaded_case is not None
    assert loaded_case.case.artifacts[0].artifact_type is ArtifactType.EMAIL
    reloaded_repository.close()


def test_list_keeps_primary_artifact_type(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    pdf_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    pdf_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        )
    )
    email_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    email_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/cc/dd/file.eml"),
        )
    )
    repository.save(pdf_case, reference_number=1)
    repository.save(email_case, reference_number=2)

    cases = repository.list()

    assert cases[0].case.artifacts[0].artifact_type is ArtifactType.PDF
    assert cases[1].case.artifacts[0].artifact_type is ArtifactType.EMAIL
    repository.close()


def test_repository_persists_and_loads_multiple_artifacts_in_order(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseRepository(database_path=database_path)
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    case = Case(id=case_id)
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.eml"),
        )
    )
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.txt"),
        )
    )
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.ATTACHMENT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        )
    )
    repository.save(case, reference_number=1)
    repository.close()

    reloaded_repository = SQLiteCaseRepository(database_path=database_path)
    loaded_case = reloaded_repository.get(case_id)

    assert loaded_case is not None
    assert tuple(artifact.artifact_type for artifact in loaded_case.case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.TEXT,
        ArtifactType.ATTACHMENT,
    )
    reloaded_repository.close()


def test_repository_list_restores_all_artifacts(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.eml"),
        )
    )
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.txt"),
        )
    )
    repository.save(case, reference_number=1)

    persisted_cases = repository.list()

    assert len(persisted_cases) == 1
    assert tuple(artifact.artifact_type for artifact in persisted_cases[0].case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.TEXT,
    )
    repository.close()


def test_repository_does_not_treat_attachment_locator_as_primary_conflict(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    first_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/first.eml"),
        )
    )
    first_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.ATTACHMENT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/shared.pdf"),
        )
    )
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    second_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/cc/dd/second.eml"),
        )
    )
    second_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.ATTACHMENT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/shared.pdf"),
        )
    )

    repository.save(first_case, reference_number=1)
    repository.save(second_case, reference_number=2)

    assert repository.count() == 2
    repository.close()


def test_case_without_artifact_still_round_trips(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseRepository(database_path=database_path)
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    repository.save(Case(id=case_id), reference_number=1)
    repository.close()

    reloaded_repository = SQLiteCaseRepository(database_path=database_path)
    loaded_case = reloaded_repository.get(case_id)

    assert loaded_case is not None
    assert loaded_case.case.artifacts == ()
    reloaded_repository.close()


def test_repository_propagates_reference_number_integrity_error(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    repository.save(first_case, reference_number=1)

    with pytest.raises(sqlite3.IntegrityError, match="cases.reference_number"):
        repository.save(second_case, reference_number=1)

    repository.close()


def test_repository_rolls_back_transaction_after_locator_conflict(tmp_path: Path) -> None:
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

    with pytest.raises(ArtifactLocatorConflictError):
        repository.save(second_case, reference_number=2)

    third_case = Case(id=Identifier.from_string("cccccccc-cccc-cccc-cccc-cccccccccccc"))
    repository.save(third_case, reference_number=3)

    assert repository.count() == 2
    repository.close()


def test_repository_rolls_back_artifact_rows_after_integrity_error(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    first_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.eml"),
        )
    )
    first_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.txt"),
        )
    )
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    second_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.eml"),
        )
    )
    second_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/cc/dd/file.txt"),
        )
    )
    repository.save(first_case, reference_number=1)

    with pytest.raises(ArtifactLocatorConflictError):
        repository.save(second_case, reference_number=2)

    loaded_case = repository.get(first_case.id)

    assert loaded_case is not None
    assert len(loaded_case.case.artifacts) == 2
    assert repository.count() == 1
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


def test_repository_migration_adds_primary_artifact_type_and_backfills_pdf(tmp_path: Path) -> None:
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
    connection.execute(
        "INSERT INTO cases (id, reference_number, status, created_at, primary_artifact_locator) VALUES (?, ?, ?, ?, ?)",
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            1,
            "open",
            "2026-07-22T12:00:00+00:00",
            "artifacts/aa/bb/file.pdf",
        ),
    )
    connection.execute(
        "INSERT INTO cases (id, reference_number, status, created_at, primary_artifact_locator) VALUES (?, ?, ?, ?, ?)",
        (
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            2,
            "open",
            "2026-07-22T12:01:00+00:00",
            None,
        ),
    )
    connection.commit()
    connection.close()

    repository = SQLiteCaseRepository(database_path=database_path)
    repository.close()

    migrated_connection = sqlite3.connect(database_path)
    migrated_connection.row_factory = sqlite3.Row
    columns = {
        row["name"]
        for row in migrated_connection.execute("PRAGMA table_info(cases)").fetchall()
    }
    rows = migrated_connection.execute(
        """
        SELECT id, primary_artifact_locator, primary_artifact_type
        FROM cases
        ORDER BY reference_number ASC
        """
    ).fetchall()
    migrated_connection.close()

    assert "primary_artifact_type" in columns
    assert rows[0]["primary_artifact_type"] == "pdf"
    assert rows[1]["primary_artifact_type"] is None


def test_repository_migration_creates_case_artifacts_from_legacy_primary_artifact(tmp_path: Path) -> None:
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
            primary_artifact_locator TEXT,
            primary_artifact_type TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO cases (
            id,
            reference_number,
            status,
            created_at,
            primary_artifact_locator,
            primary_artifact_type
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            1,
            "open",
            "2026-07-22T12:00:00+00:00",
            "artifacts/aa/bb/file.pdf",
            "pdf",
        ),
    )
    connection.commit()
    connection.close()

    repository = SQLiteCaseRepository(database_path=database_path)
    repository.close()

    migrated_connection = sqlite3.connect(database_path)
    migrated_connection.row_factory = sqlite3.Row
    rows = migrated_connection.execute(
        """
        SELECT case_id, position, artifact_type, storage_name, locator
        FROM case_artifacts
        ORDER BY case_id ASC, position ASC
        """
    ).fetchall()
    migrated_connection.close()

    assert len(rows) == 1
    assert rows[0]["position"] == 0
    assert rows[0]["artifact_type"] == "pdf"
    assert rows[0]["storage_name"] == "filesystem"
    assert rows[0]["locator"] == "artifacts/aa/bb/file.pdf"


def test_repository_migration_to_case_artifacts_is_idempotent(tmp_path: Path) -> None:
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
            primary_artifact_locator TEXT,
            primary_artifact_type TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO cases (
            id,
            reference_number,
            status,
            created_at,
            primary_artifact_locator,
            primary_artifact_type
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            1,
            "open",
            "2026-07-22T12:00:00+00:00",
            "artifacts/aa/bb/file.pdf",
            "pdf",
        ),
    )
    connection.commit()
    connection.close()

    first_repository = SQLiteCaseRepository(database_path=database_path)
    first_repository.close()
    second_repository = SQLiteCaseRepository(database_path=database_path)
    second_repository.close()

    migrated_connection = sqlite3.connect(database_path)
    row = migrated_connection.execute("SELECT COUNT(*) FROM case_artifacts").fetchone()
    migrated_connection.close()

    assert row is not None
    assert row[0] == 1


def test_repository_update_replaces_artifact_list(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    first_case = Case(id=case_id)
    first_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.eml"),
        )
    )
    first_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.txt"),
        )
    )
    repository.save(first_case, reference_number=1)

    updated_case = Case(id=case_id)
    updated_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.eml"),
        )
    )
    updated_case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.ATTACHMENT,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/cc/dd/file.pdf"),
        )
    )
    repository.save(updated_case, reference_number=1)

    loaded_case = repository.get(case_id)

    assert loaded_case is not None
    assert tuple(artifact.artifact_type for artifact in loaded_case.case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.ATTACHMENT,
    )
    repository.close()


def test_repository_persists_display_name_and_content_type(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    artifact = Artifact(
        artifact_type=ArtifactType.ATTACHMENT,
        storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
    )
    case = Case(id=case_id)
    case.add_artifact(artifact)

    repository.save(
        case,
        reference_number=1,
        artifact_records=(
            ArtifactRecord(
                artifact=artifact,
                display_name="invoice.pdf",
                content_type="application/pdf",
            ),
        ),
    )

    loaded_case = repository.get(case_id)

    assert loaded_case is not None
    assert loaded_case.artifact_records[0].display_name == "invoice.pdf"
    assert loaded_case.artifact_records[0].content_type == "application/pdf"
    repository.close()


def test_repository_get_artifact_returns_only_requested_case_position(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first_case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    second_case_id = Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    first_artifact = Artifact(
        artifact_type=ArtifactType.EMAIL,
        storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/message.eml"),
    )
    second_artifact = Artifact(
        artifact_type=ArtifactType.EMAIL,
        storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/cc/dd/other.eml"),
    )
    first_case = Case(id=first_case_id)
    first_case.add_artifact(first_artifact)
    second_case = Case(id=second_case_id)
    second_case.add_artifact(second_artifact)
    repository.save(
        first_case,
        reference_number=1,
        artifact_records=(
            ArtifactRecord(
                artifact=first_artifact,
                display_name="message.eml",
                content_type="message/rfc822",
            ),
        ),
    )
    repository.save(
        second_case,
        reference_number=2,
        artifact_records=(
            ArtifactRecord(
                artifact=second_artifact,
                display_name="other.eml",
                content_type="message/rfc822",
            ),
        ),
    )

    loaded_artifact = repository.get_artifact(first_case_id, 0)

    assert loaded_artifact is not None
    assert loaded_artifact.case_id == first_case_id
    assert loaded_artifact.display_name == "message.eml"
    assert repository.get_artifact(first_case_id, 1) is None
    assert repository.get_artifact(Identifier.from_string("cccccccc-cccc-cccc-cccc-cccccccccccc"), 0) is None
    repository.close()


def test_repository_migration_adds_artifact_metadata_columns_and_backfills_defaults(tmp_path: Path) -> None:
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
            primary_artifact_locator TEXT,
            primary_artifact_type TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE case_artifacts (
            case_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            artifact_type TEXT NOT NULL,
            storage_name TEXT NOT NULL,
            locator TEXT NOT NULL,
            PRIMARY KEY (case_id, position)
        )
        """
    )
    rows = (
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 1, "pdf", "artifacts/aa/bb/file.pdf"),
        ("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", 2, "email", "artifacts/aa/bb/file.eml"),
        ("cccccccc-cccc-cccc-cccc-cccccccccccc", 3, "text", "artifacts/aa/bb/file.txt"),
        ("dddddddd-dddd-dddd-dddd-dddddddddddd", 4, "attachment", "artifacts/aa/bb/file.bin"),
    )
    for case_id, reference_number, artifact_type, locator in rows:
        connection.execute(
            """
            INSERT INTO cases (
                id,
                reference_number,
                status,
                created_at,
                primary_artifact_locator,
                primary_artifact_type
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (case_id, reference_number, "open", "2026-07-22T12:00:00+00:00", locator, artifact_type),
        )
        connection.execute(
            """
            INSERT INTO case_artifacts (case_id, position, artifact_type, storage_name, locator)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, 0, artifact_type, "filesystem", locator),
        )
    connection.commit()
    connection.close()

    first_repository = SQLiteCaseRepository(database_path=database_path)
    first_repository.close()
    second_repository = SQLiteCaseRepository(database_path=database_path)
    second_repository.close()

    migrated_connection = sqlite3.connect(database_path)
    migrated_connection.row_factory = sqlite3.Row
    columns = {
        row["name"]
        for row in migrated_connection.execute("PRAGMA table_info(case_artifacts)").fetchall()
    }
    metadata_rows = migrated_connection.execute(
        """
        SELECT artifact_type, display_name, content_type
        FROM case_artifacts
        ORDER BY case_id ASC
        """
    ).fetchall()
    migrated_connection.close()

    assert {"display_name", "content_type"}.issubset(columns)
    assert [(row["artifact_type"], row["display_name"], row["content_type"]) for row in metadata_rows] == [
        ("pdf", "document.pdf", "application/pdf"),
        ("email", "message.eml", "message/rfc822"),
        ("text", "message.txt", "text/plain; charset=utf-8"),
        ("attachment", "attachment.bin", "application/octet-stream"),
    ]


def test_repository_persists_source_position_and_truncation(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    source_artifact = Artifact(
        artifact_type=ArtifactType.ATTACHMENT,
        storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/source.pdf"),
    )
    text_artifact = Artifact(
        artifact_type=ArtifactType.TEXT,
        storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/source.txt"),
    )
    case = Case(id=case_id)
    case.add_artifact(source_artifact)
    case.add_artifact(text_artifact)

    repository.save(
        case,
        reference_number=1,
        artifact_records=(
            ArtifactRecord(
                artifact=source_artifact,
                display_name="source.pdf",
                content_type="application/pdf",
            ),
            ArtifactRecord(
                artifact=text_artifact,
                display_name="source.txt",
                content_type="text/plain; charset=utf-8",
                source_position=0,
                is_truncated=True,
            ),
        ),
    )

    loaded_case = repository.get(case_id)
    downloadable = repository.get_artifact(case_id, 1)

    assert loaded_case is not None
    assert loaded_case.artifact_records[1].source_position == 0
    assert loaded_case.artifact_records[1].is_truncated is True
    assert downloadable is not None
    assert downloadable.source_position == 0
    assert downloadable.is_truncated is True
    repository.close()


def test_repository_migration_adds_source_position_and_is_truncated_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE cases (
            id TEXT PRIMARY KEY,
            reference_number INTEGER UNIQUE NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE case_artifacts (
            case_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            artifact_type TEXT NOT NULL,
            storage_name TEXT NOT NULL,
            locator TEXT NOT NULL,
            display_name TEXT,
            content_type TEXT,
            PRIMARY KEY (case_id, position)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO case_artifacts (
            case_id,
            position,
            artifact_type,
            storage_name,
            locator,
            display_name,
            content_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            0,
            "attachment",
            "filesystem",
            "artifacts/aa/bb/source.pdf",
            "source.pdf",
            "application/pdf",
        ),
    )
    connection.commit()
    connection.close()

    first_repository = SQLiteCaseRepository(database_path=database_path)
    first_repository.close()
    second_repository = SQLiteCaseRepository(database_path=database_path)
    second_repository.close()

    migrated_connection = sqlite3.connect(database_path)
    migrated_connection.row_factory = sqlite3.Row
    columns = {
        row["name"]
        for row in migrated_connection.execute("PRAGMA table_info(case_artifacts)").fetchall()
    }
    row = migrated_connection.execute(
        "SELECT source_position, is_truncated FROM case_artifacts WHERE case_id = ? AND position = 0",
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",),
    ).fetchone()
    migrated_connection.close()

    assert {"source_position", "is_truncated"}.issubset(columns)
    assert row is not None
    assert row["source_position"] is None
    assert row["is_truncated"] == 0


def test_repository_raises_for_unknown_artifact_type_in_case_artifacts(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseRepository(database_path=database_path)
    repository.close()

    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        INSERT INTO cases (id, reference_number, status, created_at, primary_artifact_locator, primary_artifact_type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            1,
            "open",
            "2026-07-22T12:00:00+00:00",
            "artifacts/aa/bb/file.unknown",
            "unknown",
        ),
    )
    connection.execute(
        """
        INSERT INTO case_artifacts (case_id, position, artifact_type, storage_name, locator)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            0,
            "unknown",
            "filesystem",
            "artifacts/aa/bb/file.unknown",
        ),
    )
    connection.commit()
    connection.close()

    reloaded_repository = SQLiteCaseRepository(database_path=database_path)

    with pytest.raises(ValueError):
        reloaded_repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    reloaded_repository.close()
