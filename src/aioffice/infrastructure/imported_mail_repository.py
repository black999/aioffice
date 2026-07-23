"""SQLite persistence for imported mailbox messages."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from aioffice.application import ImportedMailConflictError, ImportedMailRepository
from aioffice.domain import Identifier


@dataclass(slots=True)
class SQLiteImportedMailRepository(ImportedMailRepository):
    """Store imported mailbox message identifiers in SQLite."""

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

    def has_imported(self, mailbox_identity: str, uid: str) -> bool:
        """Return whether a mailbox UID has already been imported."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT 1
                FROM imported_mail
                WHERE mailbox_identity = ? AND uid = ?
                """,
                (mailbox_identity, uid),
            ).fetchone()
            return row is not None

    def save_import(
        self,
        mailbox_identity: str,
        uid: str,
        message_id: str | None,
        case_id: Identifier,
    ) -> None:
        """Persist a mailbox import record."""

        with self._lock:
            try:
                self._connection.execute(
                    """
                    INSERT INTO imported_mail (
                        mailbox_identity,
                        uid,
                        message_id,
                        case_id,
                        imported_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        mailbox_identity,
                        uid,
                        message_id,
                        str(case_id),
                        datetime.now(UTC).isoformat(timespec="seconds"),
                    ),
                )
                self._connection.commit()
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                if self._is_primary_key_conflict(error):
                    msg = "mailbox UID has already been imported"
                    raise ImportedMailConflictError(msg) from error
                raise

    def _create_tables(self) -> None:
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS imported_mail (
                    mailbox_identity TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    message_id TEXT,
                    case_id TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    PRIMARY KEY (mailbox_identity, uid)
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_imported_mail_message_id
                ON imported_mail(message_id)
                """
            )
            self._connection.commit()

    def _is_primary_key_conflict(self, error: sqlite3.IntegrityError) -> bool:
        message = str(error)
        return "imported_mail.mailbox_identity" in message and "imported_mail.uid" in message
