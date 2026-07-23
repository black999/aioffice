"""SQLite persistence for cases and case numbering."""

from __future__ import annotations

import sqlite3
from threading import RLock
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from aioffice.application import CaseNumberProvider, CaseRepository, PersistedCase
from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference


@dataclass(slots=True)
class SQLiteCaseRepository(CaseRepository):
    """Store cases in a local SQLite database."""

    database_path: Path
    default_status: str = "open"
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

    def save(self, case: Case, reference_number: int) -> None:
        """Persist a case with its assigned business reference number."""

        with self._lock:
            existing_row = self._connection.execute(
                "SELECT created_at FROM cases WHERE id = ?",
                (str(case.id),),
            ).fetchone()
            created_at = (
                existing_row["created_at"]
                if existing_row is not None
                else datetime.now(UTC).isoformat(timespec="seconds")
            )
            artifact_locator = case.artifacts[0].storage_reference.locator if case.artifacts else None
            self._connection.execute(
                """
                INSERT INTO cases (id, reference_number, status, created_at, primary_artifact_locator)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    reference_number = excluded.reference_number,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    primary_artifact_locator = excluded.primary_artifact_locator
                """,
                (str(case.id), reference_number, self.default_status, created_at, artifact_locator),
            )
            self._connection.commit()

    def get(self, case_id: Identifier) -> PersistedCase | None:
        """Load a persisted case by identifier."""

        with self._lock:
            row = self._connection.execute(
                "SELECT id, reference_number, status, created_at, primary_artifact_locator FROM cases WHERE id = ?",
                (str(case_id),),
            ).fetchone()
            if row is None:
                return None
            return self._build_persisted_case(row)

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        """Load a persisted case by its primary artifact locator."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, reference_number, status, created_at, primary_artifact_locator
                FROM cases
                WHERE primary_artifact_locator = ?
                LIMIT 1
                """,
                (locator,),
            ).fetchone()
            if row is None:
                return None
            return self._build_persisted_case(row)

    def list(self) -> tuple[PersistedCase, ...]:
        """List all persisted cases."""

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, reference_number, status, created_at, primary_artifact_locator
                FROM cases
                ORDER BY reference_number ASC
                """,
            ).fetchall()
            return tuple(self._build_persisted_case(row) for row in rows)

    def count(self) -> int:
        """Count all persisted cases."""

        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS total FROM cases").fetchone()
            if row is None:
                return 0
            return int(row["total"])

    def _build_persisted_case(self, row: sqlite3.Row) -> PersistedCase:
        case = Case(id=Identifier.from_string(row["id"]))
        if row["primary_artifact_locator"] is not None:
            artifact = Artifact(
                artifact_type=ArtifactType.PDF,
                storage_reference=StorageReference(
                    storage_name="filesystem",
                    locator=row["primary_artifact_locator"],
                ),
            )
            case.add_artifact(artifact)
            case.pull_events()
        return PersistedCase(
            case=case,
            reference_number=int(row["reference_number"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
        )

    def _create_tables(self) -> None:
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    reference_number INTEGER UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    primary_artifact_locator TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(cases)").fetchall()
            }
            if "reference_number" not in columns:
                self._connection.execute("ALTER TABLE cases ADD COLUMN reference_number INTEGER")
                self._connection.execute(
                    "UPDATE cases SET reference_number = rowid WHERE reference_number IS NULL"
                )
                self._connection.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_cases_reference_number
                    ON cases(reference_number)
                    """
                )
            if "primary_artifact_locator" not in columns:
                self._connection.execute("ALTER TABLE cases ADD COLUMN primary_artifact_locator TEXT")
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_cases_primary_artifact_locator
                ON cases(primary_artifact_locator)
                """
            )
            duplicate_locator_row = self._connection.execute(
                """
                SELECT primary_artifact_locator
                FROM cases
                WHERE primary_artifact_locator IS NOT NULL
                GROUP BY primary_artifact_locator
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            ).fetchone()
            if duplicate_locator_row is not None:
                duplicate_locator = str(duplicate_locator_row["primary_artifact_locator"])
                msg = (
                    "Cannot create unique locator index because duplicate "
                    f"primary_artifact_locator values already exist: {duplicate_locator}"
                )
                raise RuntimeError(msg)
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_cases_primary_artifact_locator
                ON cases(primary_artifact_locator)
                WHERE primary_artifact_locator IS NOT NULL
                """
            )
            self._connection.commit()


@dataclass(slots=True)
class SQLiteCaseNumberProvider(CaseNumberProvider):
    """Allocate sequential case numbers in SQLite."""

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

    def next_number(self) -> int:
        """Allocate the next sequential business case number."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT next_value FROM case_number_sequence WHERE sequence_name = ?",
                    ("case_reference",),
                ).fetchone()
                if row is None:
                    msg = "case number sequence is not initialized"
                    raise RuntimeError(msg)
                current_value = int(row["next_value"])
                self._connection.execute(
                    "UPDATE case_number_sequence SET next_value = ? WHERE sequence_name = ?",
                    (current_value + 1, "case_reference"),
                )
                self._connection.commit()
                return current_value
            except Exception:
                self._connection.rollback()
                raise

    def _create_tables(self) -> None:
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS case_number_sequence (
                    sequence_name TEXT PRIMARY KEY,
                    next_value INTEGER NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                INSERT INTO case_number_sequence (sequence_name, next_value)
                VALUES (?, ?)
                ON CONFLICT(sequence_name) DO NOTHING
                """,
                ("case_reference", 1),
            )
            has_cases_table = self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
                ("table", "cases"),
            ).fetchone()
            max_reference_number = 0
            if has_cases_table is not None:
                max_reference_number_row = self._connection.execute(
                    "SELECT MAX(reference_number) AS max_reference_number FROM cases",
                ).fetchone()
                max_reference_number = (
                    int(max_reference_number_row["max_reference_number"])
                    if max_reference_number_row is not None and max_reference_number_row["max_reference_number"] is not None
                    else 0
                )
            minimum_next_value = max_reference_number + 1
            self._connection.execute(
                """
                UPDATE case_number_sequence
                SET next_value = CASE
                    WHEN next_value < ? THEN ?
                    ELSE next_value
                END
                WHERE sequence_name = ?
                """,
                (minimum_next_value, minimum_next_value, "case_reference"),
            )
            self._connection.commit()
