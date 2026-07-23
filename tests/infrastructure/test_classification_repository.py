import sqlite3
from pathlib import Path

import pytest

from aioffice.application import CaseCategory, PersistedCaseClassification
from aioffice.domain import Identifier
from aioffice.infrastructure import SQLiteCaseClassificationRepository


def _classification(case_id: str, *, category: CaseCategory = CaseCategory.INVOICE) -> PersistedCaseClassification:
    return PersistedCaseClassification(
        case_id=Identifier.from_string(case_id),
        category=category,
        confidence=0.92,
        rationale="Invoice-related content",
        model_name="qwen2.5:7b",
        classified_at="2026-07-23T12:00:00+00:00",
    )


def test_classification_repository_creates_table_and_round_trips(tmp_path: Path) -> None:
    repository = SQLiteCaseClassificationRepository(database_path=tmp_path / "storage" / "aioffice.db")
    classification = _classification("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    repository.save(classification)
    loaded = repository.get(classification.case_id)

    assert loaded == classification
    repository.close()


def test_classification_repository_upsert_replaces_previous_result(tmp_path: Path) -> None:
    repository = SQLiteCaseClassificationRepository(database_path=tmp_path / "storage" / "aioffice.db")
    case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    repository.save(_classification(case_id, category=CaseCategory.INVOICE))
    repository.save(_classification(case_id, category=CaseCategory.REQUEST))

    loaded = repository.get(Identifier.from_string(case_id))

    assert loaded is not None
    assert loaded.category is CaseCategory.REQUEST
    repository.close()


def test_classification_repository_delete_removes_result(tmp_path: Path) -> None:
    repository = SQLiteCaseClassificationRepository(database_path=tmp_path / "storage" / "aioffice.db")
    classification = _classification("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    repository.save(classification)

    repository.delete(classification.case_id)

    assert repository.get(classification.case_id) is None
    repository.close()


def test_classification_repository_get_many_returns_batch(tmp_path: Path) -> None:
    repository = SQLiteCaseClassificationRepository(database_path=tmp_path / "storage" / "aioffice.db")
    first = _classification("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    second = _classification("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", category=CaseCategory.REQUEST)
    repository.save(first)
    repository.save(second)

    loaded = repository.get_many((first.case_id, second.case_id))

    assert loaded[first.case_id].category is CaseCategory.INVOICE
    assert loaded[second.case_id].category is CaseCategory.REQUEST
    repository.close()


def test_classification_repository_rejects_unknown_category_in_storage(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseClassificationRepository(database_path=database_path)
    repository.close()

    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        INSERT INTO case_classifications (case_id, category, confidence, rationale, model_name, classified_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "unknown", 0.5, "x", "model", "2026-07-23T12:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    reloaded = SQLiteCaseClassificationRepository(database_path=database_path)

    with pytest.raises(RuntimeError, match="unknown category"):
        reloaded.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    reloaded.close()


def test_classification_repository_rejects_invalid_confidence_in_storage(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteCaseClassificationRepository(database_path=database_path)
    repository.close()

    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        INSERT INTO case_classifications (case_id, category, confidence, rationale, model_name, classified_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "invoice", 5.0, "x", "model", "2026-07-23T12:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    reloaded = SQLiteCaseClassificationRepository(database_path=database_path)

    with pytest.raises(RuntimeError, match="invalid data"):
        reloaded.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    reloaded.close()
