"""SQLite persistence for case classifications."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from aioffice.application import CaseCategory, CaseClassificationRepository, PersistedCaseClassification
from aioffice.domain import Identifier


@dataclass(slots=True)
class SQLiteCaseClassificationRepository(CaseClassificationRepository):
    """Persist the latest classification result per case in SQLite."""

    database_path: Path
    _connection: sqlite3.Connection = field(init=False, repr=False)
    _lock: RLock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.database_path = self.database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        with self._lock:
            self._connection.close()

    def save(self, classification: PersistedCaseClassification) -> None:
        """Persist or replace a case classification."""

        with self._lock:
            self._connection.execute(
                """
                INSERT INTO case_classifications (
                    case_id,
                    category,
                    confidence,
                    rationale,
                    model_name,
                    classified_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    category = excluded.category,
                    confidence = excluded.confidence,
                    rationale = excluded.rationale,
                    model_name = excluded.model_name,
                    classified_at = excluded.classified_at
                """,
                (
                    str(classification.case_id),
                    classification.category.value,
                    classification.confidence,
                    classification.rationale,
                    classification.model_name,
                    classification.classified_at,
                ),
            )
            self._connection.commit()

    def get(self, case_id: Identifier) -> PersistedCaseClassification | None:
        """Load a case classification if it exists."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT case_id, category, confidence, rationale, model_name, classified_at
                FROM case_classifications
                WHERE case_id = ?
                """,
                (str(case_id),),
            ).fetchone()
            if row is None:
                return None
            return self._build_persisted_classification(row)

    def get_many(
        self,
        case_ids: tuple[Identifier, ...],
    ) -> dict[Identifier, PersistedCaseClassification]:
        """Load classifications for many cases in one call."""

        if not case_ids:
            return {}
        placeholders = ", ".join("?" for _ in case_ids)
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT case_id, category, confidence, rationale, model_name, classified_at
                FROM case_classifications
                WHERE case_id IN ({placeholders})
                """,
                tuple(str(case_id) for case_id in case_ids),
            ).fetchall()
        return {
            Identifier.from_string(str(row["case_id"])): self._build_persisted_classification(row)
            for row in rows
        }

    def delete(self, case_id: Identifier) -> None:
        """Delete a case classification if it exists."""

        with self._lock:
            self._connection.execute("DELETE FROM case_classifications WHERE case_id = ?", (str(case_id),))
            self._connection.commit()

    def _create_tables(self) -> None:
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS case_classifications (
                    case_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    classified_at TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES cases(id)
                )
                """
            )
            self._connection.commit()

    def _build_persisted_classification(self, row: sqlite3.Row) -> PersistedCaseClassification:
        try:
            category = CaseCategory(str(row["category"]))
        except ValueError as error:
            msg = "stored classification contains an unknown category"
            raise RuntimeError(msg) from error

        try:
            return PersistedCaseClassification(
                case_id=Identifier.from_string(str(row["case_id"])),
                category=category,
                confidence=float(row["confidence"]),
                rationale=str(row["rationale"]),
                model_name=str(row["model_name"]),
                classified_at=str(row["classified_at"]),
            )
        except ValueError as error:
            msg = "stored classification contains invalid data"
            raise RuntimeError(msg) from error
