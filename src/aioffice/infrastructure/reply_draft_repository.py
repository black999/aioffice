"""SQLite persistence for reply drafts."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from aioffice.application import PersistedReplyDraft, ReplyDraftRepository, ReplyDraftStatus
from aioffice.domain import Identifier


@dataclass(slots=True)
class SQLiteReplyDraftRepository(ReplyDraftRepository):
    """Persist the latest reply draft per case in SQLite."""

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

    def save(self, draft: PersistedReplyDraft) -> None:
        """Persist or replace a reply draft."""

        with self._lock:
            self._connection.execute(
                """
                INSERT INTO reply_drafts (
                    case_id,
                    subject,
                    body,
                    status,
                    model_name,
                    operator_instruction,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    subject = excluded.subject,
                    body = excluded.body,
                    status = excluded.status,
                    model_name = excluded.model_name,
                    operator_instruction = excluded.operator_instruction,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    str(draft.case_id),
                    draft.subject,
                    draft.body,
                    draft.status.value,
                    draft.model_name,
                    draft.operator_instruction,
                    draft.created_at,
                    draft.updated_at,
                ),
            )
            self._connection.commit()

    def get(self, case_id: Identifier) -> PersistedReplyDraft | None:
        """Load a reply draft if it exists."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    case_id,
                    subject,
                    body,
                    status,
                    model_name,
                    operator_instruction,
                    created_at,
                    updated_at
                FROM reply_drafts
                WHERE case_id = ?
                """,
                (str(case_id),),
            ).fetchone()
        if row is None:
            return None
        return self._build_persisted_draft(row)

    def get_statuses(
        self,
        case_ids: tuple[Identifier, ...],
    ) -> dict[Identifier, ReplyDraftStatus]:
        """Load reply draft statuses for many cases in one call."""

        if not case_ids:
            return {}
        placeholders = ", ".join("?" for _ in case_ids)
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT case_id, status
                FROM reply_drafts
                WHERE case_id IN ({placeholders})
                """,
                tuple(str(case_id) for case_id in case_ids),
            ).fetchall()
        statuses: dict[Identifier, ReplyDraftStatus] = {}
        for row in rows:
            try:
                status = ReplyDraftStatus(str(row["status"]))
            except ValueError as error:
                msg = "stored reply draft contains an unknown status"
                raise RuntimeError(msg) from error
            statuses[Identifier.from_string(str(row["case_id"]))] = status
        return statuses

    def delete(self, case_id: Identifier) -> None:
        """Delete the current reply draft for a case."""

        with self._lock:
            self._connection.execute("DELETE FROM reply_drafts WHERE case_id = ?", (str(case_id),))
            self._connection.commit()

    def _create_tables(self) -> None:
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reply_drafts (
                    case_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    operator_instruction TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES cases(id)
                )
                """
            )
            self._connection.commit()

    def _build_persisted_draft(self, row: sqlite3.Row) -> PersistedReplyDraft:
        try:
            status = ReplyDraftStatus(str(row["status"]))
        except ValueError as error:
            msg = "stored reply draft contains an unknown status"
            raise RuntimeError(msg) from error

        try:
            return PersistedReplyDraft(
                case_id=Identifier.from_string(str(row["case_id"])),
                subject=str(row["subject"]),
                body=str(row["body"]),
                status=status,
                model_name=str(row["model_name"]),
                operator_instruction=(
                    None if row["operator_instruction"] is None else str(row["operator_instruction"])
                ),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
        except ValueError as error:
            msg = "stored reply draft contains invalid data"
            raise RuntimeError(msg) from error
