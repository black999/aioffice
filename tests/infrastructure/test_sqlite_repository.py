from pathlib import Path

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

    repository.save(case)

    assert repository.count() == 1
    repository.close()


def test_load_case_returns_case_by_identifier(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    repository.save(Case(id=case_id))

    loaded_case = repository.get(case_id)

    assert loaded_case is not None
    assert loaded_case.id == case_id
    assert loaded_case.artifacts == ()
    repository.close()


def test_list_cases_returns_all_persisted_cases(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    repository.save(first_case)
    repository.save(second_case)

    cases = repository.list()

    assert tuple(case.id for case in cases) == (first_case.id, second_case.id)
    repository.close()


def test_repository_persists_after_reopening(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    first_repository = SQLiteCaseRepository(database_path=database_path)
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    first_repository.save(Case(id=case_id))
    first_repository.close()

    second_repository = SQLiteCaseRepository(database_path=database_path)

    assert second_repository.count() == 1
    loaded_case = second_repository.get(case_id)
    assert loaded_case is not None
    assert loaded_case.id == case_id
    second_repository.close()


def test_empty_repository_returns_no_cases(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")

    assert repository.count() == 0
    assert repository.list() == ()
    assert repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")) is None
    repository.close()
