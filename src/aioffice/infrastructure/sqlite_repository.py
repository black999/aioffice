"""SQLite persistence for cases and case numbering."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from aioffice.application import (
    ArtifactLocatorConflictError,
    CaseNumberProvider,
    CaseRepository,
    PersistedCase,
)
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
            try:
                existing_row = self._connection.execute(
                    "SELECT created_at FROM cases WHERE id = ?",
                    (str(case.id),),
                ).fetchone()
                created_at = (
                    existing_row["created_at"]
                    if existing_row is not None
                    else datetime.now(UTC).isoformat(timespec="seconds")
                )
                if case.artifacts:
                    primary_artifact = case.artifacts[0]
                    artifact_locator = primary_artifact.storage_reference.locator
                    artifact_type = primary_artifact.artifact_type.value
                else:
                    artifact_locator = None
                    artifact_type = None
                self._connection.execute(
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
                    ON CONFLICT(id) DO UPDATE SET
                        reference_number = excluded.reference_number,
                        status = excluded.status,
                        created_at = excluded.created_at,
                        primary_artifact_locator = excluded.primary_artifact_locator,
                        primary_artifact_type = excluded.primary_artifact_type
                    """,
                    (
                        str(case.id),
                        reference_number,
                        self.default_status,
                        created_at,
                        artifact_locator,
                        artifact_type,
                    ),
                )
                self._connection.execute("DELETE FROM case_artifacts WHERE case_id = ?", (str(case.id),))
                artifact_rows = [
                    (
                        str(case.id),
                        position,
                        artifact.artifact_type.value,
                        artifact.storage_reference.storage_name,
                        artifact.storage_reference.locator,
                    )
                    for position, artifact in enumerate(case.artifacts)
                ]
                if artifact_rows:
                    self._connection.executemany(
                        """
                        INSERT INTO case_artifacts (
                            case_id,
                            position,
                            artifact_type,
                            storage_name,
                            locator
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        artifact_rows,
                    )
                self._connection.commit()
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                if self._is_artifact_locator_conflict(error):
                    msg = "artifact locator is already assigned to another case"
                    raise ArtifactLocatorConflictError(msg) from error
                raise

    def get(self, case_id: Identifier) -> PersistedCase | None:
        """Load a persisted case by identifier."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    id,
                    reference_number,
                    status,
                    created_at,
                    primary_artifact_locator,
                    primary_artifact_type
                FROM cases
                WHERE id = ?
                """,
                (str(case_id),),
            ).fetchone()
            if row is None:
                return None
            artifact_rows = self._load_artifact_rows((str(case_id),))
            return self._build_persisted_case(row, artifact_rows)

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        """Load a persisted case by its primary artifact locator."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    c.id,
                    c.reference_number,
                    c.status,
                    c.created_at,
                    c.primary_artifact_locator,
                    c.primary_artifact_type
                FROM cases AS c
                INNER JOIN case_artifacts AS a
                    ON a.case_id = c.id
                WHERE a.position = 0
                  AND a.locator = ?
                LIMIT 1
                """,
                (locator,),
            ).fetchone()
            if row is None:
                return None
            artifact_rows = self._load_artifact_rows((str(row["id"]),))
            return self._build_persisted_case(row, artifact_rows)

    def list(self) -> tuple[PersistedCase, ...]:
        """List all persisted cases."""

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT
                    id,
                    reference_number,
                    status,
                    created_at,
                    primary_artifact_locator,
                    primary_artifact_type
                FROM cases
                ORDER BY reference_number ASC
                """,
            ).fetchall()
            if not rows:
                return ()
            case_ids = tuple(str(row["id"]) for row in rows)
            artifact_rows = self._load_artifact_rows(case_ids)
            artifacts_by_case_id: dict[str, list[sqlite3.Row]] = {}
            for artifact_row in artifact_rows:
                artifacts_by_case_id.setdefault(str(artifact_row["case_id"]), []).append(artifact_row)
            return tuple(
                self._build_persisted_case(row, tuple(artifacts_by_case_id.get(str(row["id"]), ())))
                for row in rows
            )

    def count(self) -> int:
        """Count all persisted cases."""

        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS total FROM cases").fetchone()
            if row is None:
                return 0
            return int(row["total"])

    def _build_persisted_case(
        self,
        row: sqlite3.Row,
        artifact_rows: tuple[sqlite3.Row, ...],
    ) -> PersistedCase:
        case = Case(id=Identifier.from_string(row["id"]))
        for artifact_row in artifact_rows:
            artifact_type = ArtifactType(str(artifact_row["artifact_type"]))
            artifact = Artifact(
                artifact_type=artifact_type,
                storage_reference=StorageReference(
                    storage_name=str(artifact_row["storage_name"]),
                    locator=str(artifact_row["locator"]),
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

    def _is_artifact_locator_conflict(self, error: sqlite3.IntegrityError) -> bool:
        message = str(error)
        return (
            "cases.primary_artifact_locator" in message
            or "ux_cases_primary_artifact_locator" in message
            or "ux_case_artifacts_primary_locator" in message
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
                    primary_artifact_locator TEXT,
                    primary_artifact_type TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS case_artifacts (
                    case_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    artifact_type TEXT NOT NULL,
                    storage_name TEXT NOT NULL,
                    locator TEXT NOT NULL,
                    PRIMARY KEY (case_id, position),
                    FOREIGN KEY (case_id) REFERENCES cases(id)
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
            if "primary_artifact_type" not in columns:
                self._connection.execute("ALTER TABLE cases ADD COLUMN primary_artifact_type TEXT")
                self._connection.execute(
                    """
                    UPDATE cases
                    SET primary_artifact_type = ?
                    WHERE primary_artifact_locator IS NOT NULL
                      AND primary_artifact_type IS NULL
                    """,
                    (ArtifactType.PDF.value,),
                )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_cases_primary_artifact_locator
                ON cases(primary_artifact_locator)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_case_artifacts_locator
                ON case_artifacts(locator)
                """
            )
            self._connection.execute(
                """
                INSERT INTO case_artifacts (
                    case_id,
                    position,
                    artifact_type,
                    storage_name,
                    locator
                )
                SELECT
                    cases.id,
                    0,
                    COALESCE(cases.primary_artifact_type, ?),
                    'filesystem',
                    cases.primary_artifact_locator
                FROM cases
                WHERE cases.primary_artifact_locator IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1
                    FROM case_artifacts
                    WHERE case_artifacts.case_id = cases.id
                      AND case_artifacts.position = 0
                  )
                """,
                (ArtifactType.PDF.value,),
            )
            duplicate_locator_row = self._connection.execute(
                """
                SELECT locator
                FROM case_artifacts
                WHERE position = 0
                GROUP BY locator
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            ).fetchone()
            if duplicate_locator_row is not None:
                duplicate_locator = str(duplicate_locator_row["locator"])
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
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_case_artifacts_primary_locator
                ON case_artifacts(locator)
                WHERE position = 0
                """
            )
            self._connection.commit()

    def _load_artifact_rows(self, case_ids: tuple[str, ...]) -> tuple[sqlite3.Row, ...]:
        if not case_ids:
            return ()
        placeholders = ", ".join("?" for _ in case_ids)
        rows = self._connection.execute(
            f"""
            SELECT case_id, position, artifact_type, storage_name, locator
            FROM case_artifacts
            WHERE case_id IN ({placeholders})
            ORDER BY case_id ASC, position ASC
            """,
            case_ids,
        ).fetchall()
        return tuple(rows)


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
