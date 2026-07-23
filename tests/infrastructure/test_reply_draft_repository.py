import sqlite3
from pathlib import Path

import pytest

from aioffice.application import PersistedReplyDraft, ReplyDraftStatus
from aioffice.domain import Case, Identifier
from aioffice.infrastructure import SQLiteCaseRepository, SQLiteReplyDraftRepository


def _save_case(database_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=database_path)
    repository.save(
        Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        reference_number=1,
    )
    repository.close()


def _draft(
    *,
    status: ReplyDraftStatus = ReplyDraftStatus.GENERATED,
    approved_by: str | None = None,
    approved_at: str | None = None,
) -> PersistedReplyDraft:
    return PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Temat",
        body="Tresc",
        status=status,
        model_name="qwen3:4b",
        operator_instruction="Uprzejmie",
        approved_by=approved_by,
        approved_at=approved_at,
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:00:00+00:00",
    )


def _create_legacy_reply_drafts_table(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE reply_drafts (
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
    connection.commit()
    connection.close()


def test_reply_draft_repository_creates_table_and_roundtrips_draft(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository.save(_draft())

    loaded = repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert loaded is not None
    assert loaded.subject == "Temat"
    assert loaded.status is ReplyDraftStatus.GENERATED
    assert loaded.approved_by is None
    assert loaded.approved_at is None
    repository.close()


def test_reply_draft_repository_migration_adds_approval_columns_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    _create_legacy_reply_drafts_table(database_path)

    first_repository = SQLiteReplyDraftRepository(database_path=database_path)
    first_repository.close()
    second_repository = SQLiteReplyDraftRepository(database_path=database_path)

    columns = {
        str(row["name"])
        for row in second_repository._connection.execute("PRAGMA table_info(reply_drafts)").fetchall()
    }

    assert "approved_by" in columns
    assert "approved_at" in columns
    second_repository.close()


def test_reply_draft_repository_preserves_legacy_records_without_approval(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    _create_legacy_reply_drafts_table(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        INSERT INTO reply_drafts (
            case_id, subject, body, status, model_name, operator_instruction, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "Temat",
            "Tresc",
            "generated",
            "qwen3:4b",
            None,
            "2026-07-23T10:00:00+00:00",
            "2026-07-23T10:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()

    repository = SQLiteReplyDraftRepository(database_path=database_path)
    loaded = repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert loaded is not None
    assert loaded.status is ReplyDraftStatus.GENERATED
    assert loaded.approved_by is None
    assert loaded.approved_at is None
    repository.close()


def test_reply_draft_repository_upserts_and_can_clear_approval(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository.save(
        _draft(
            status=ReplyDraftStatus.APPROVED,
            approved_by="Jan Kowalski",
            approved_at="2026-07-23T10:05:00+00:00",
        )
    )
    repository.save(
        PersistedReplyDraft(
            case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            subject="Nowy temat",
            body="Nowa tresc",
            status=ReplyDraftStatus.EDITED,
            model_name="qwen3:4b",
            operator_instruction=None,
            approved_by=None,
            approved_at=None,
            created_at="2026-07-23T10:00:00+00:00",
            updated_at="2026-07-23T11:00:00+00:00",
        )
    )

    loaded = repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert loaded is not None
    assert loaded.subject == "Nowy temat"
    assert loaded.status is ReplyDraftStatus.EDITED
    assert loaded.created_at == "2026-07-23T10:00:00+00:00"
    assert loaded.updated_at == "2026-07-23T11:00:00+00:00"
    assert loaded.approved_by is None
    assert loaded.approved_at is None
    repository.close()


def test_reply_draft_repository_roundtrips_approved_draft(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository.save(
        _draft(
            status=ReplyDraftStatus.APPROVED,
            approved_by="Jan Kowalski",
            approved_at="2026-07-23T10:05:00+00:00",
        )
    )

    loaded = repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert loaded is not None
    assert loaded.status is ReplyDraftStatus.APPROVED
    assert loaded.approved_by == "Jan Kowalski"
    assert loaded.approved_at == "2026-07-23T10:05:00+00:00"
    repository.close()


def test_reply_draft_repository_get_statuses_returns_batch_mapping(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository.save(
        _draft(
            status=ReplyDraftStatus.APPROVED,
            approved_by="Jan Kowalski",
            approved_at="2026-07-23T10:05:00+00:00",
        )
    )

    statuses = repository.get_statuses(
        (Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),)
    )

    assert statuses == {
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"): ReplyDraftStatus.APPROVED
    }
    repository.close()


def test_reply_draft_repository_delete_removes_draft(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository.save(_draft())

    repository.delete(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")) is None
    repository.close()


def test_reply_draft_repository_rejects_unknown_status_in_database(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository._connection.execute(
        """
        INSERT INTO reply_drafts (
            case_id,
            subject,
            body,
            status,
            model_name,
            operator_instruction,
            approved_by,
            approved_at,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "Temat",
            "Tresc",
            "broken",
            "qwen3:4b",
            None,
            None,
            None,
            "2026-07-23T10:00:00+00:00",
            "2026-07-23T10:00:00+00:00",
        ),
    )
    repository._connection.commit()

    with pytest.raises(RuntimeError, match="unknown status"):
        repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    repository.close()


def test_reply_draft_repository_rejects_inconsistent_approved_record_on_read(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository._connection.execute(
        """
        INSERT INTO reply_drafts (
            case_id,
            subject,
            body,
            status,
            model_name,
            operator_instruction,
            approved_by,
            approved_at,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "Temat",
            "Tresc",
            "approved",
            "qwen3:4b",
            None,
            None,
            "2026-07-23T10:05:00+00:00",
            "2026-07-23T10:00:00+00:00",
            "2026-07-23T10:05:00+00:00",
        ),
    )
    repository._connection.commit()

    with pytest.raises(RuntimeError, match="invalid data"):
        repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    repository.close()
