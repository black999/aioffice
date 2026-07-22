"""SQLite persistence for cases."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from aioffice.application import CaseRepository
from aioffice.domain import Case, Identifier


@dataclass(slots=True)
class SQLiteCaseRepository(CaseRepository):
    """Store cases in a local SQLite database."""

    database_path: Path
    default_status: str = "open"
    _connection: sqlite3.Connection = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.database_path = self.database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    def save(self, case: Case) -> None:
        """Persist a case."""

        existing_row = self._connection.execute(
            "SELECT created_at FROM cases WHERE id = ?",
            (str(case.id),),
        ).fetchone()
        created_at = (
            existing_row["created_at"]
            if existing_row is not None
            else datetime.now(UTC).isoformat(timespec="seconds")
        )
        self._connection.execute(
            """
            INSERT INTO cases (id, status, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                created_at = excluded.created_at
            """,
            (str(case.id), self.default_status, created_at),
        )
        self._connection.commit()

    def get(self, case_id: Identifier) -> Case | None:
        """Load a case by identifier."""

        row = self._connection.execute(
            "SELECT id FROM cases WHERE id = ?",
            (str(case_id),),
        ).fetchone()
        if row is None:
            return None
        return Case(id=Identifier.from_string(row["id"]))

    def list(self) -> tuple[Case, ...]:
        """List all persisted cases."""

        rows = self._connection.execute(
            "SELECT id FROM cases ORDER BY created_at ASC, id ASC",
        ).fetchall()
        return tuple(Case(id=Identifier.from_string(row["id"])) for row in rows)

    def count(self) -> int:
        """Count all persisted cases."""

        row = self._connection.execute("SELECT COUNT(*) AS total FROM cases").fetchone()
        if row is None:
            return 0
        return int(row["total"])

    def _create_tables(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()
