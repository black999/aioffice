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


def _draft(*, status: ReplyDraftStatus = ReplyDraftStatus.GENERATED) -> PersistedReplyDraft:
    return PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Temat",
        body="Tresc",
        status=status,
        model_name="qwen3:4b",
        operator_instruction="Uprzejmie",
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:00:00+00:00",
    )


def test_reply_draft_repository_creates_table_and_roundtrips_draft(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository.save(_draft())

    loaded = repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert loaded is not None
    assert loaded.subject == "Temat"
    assert loaded.status is ReplyDraftStatus.GENERATED
    repository.close()


def test_reply_draft_repository_upserts_and_preserves_created_at_when_passed_in(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository.save(_draft())
    repository.save(
        PersistedReplyDraft(
            case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            subject="Nowy temat",
            body="Nowa tresc",
            status=ReplyDraftStatus.EDITED,
            model_name="qwen3:4b",
            operator_instruction=None,
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
    repository.close()


def test_reply_draft_repository_get_statuses_returns_batch_mapping(tmp_path: Path) -> None:
    database_path = tmp_path / "aioffice.db"
    _save_case(database_path)
    repository = SQLiteReplyDraftRepository(database_path=database_path)
    repository.save(_draft(status=ReplyDraftStatus.EDITED))

    statuses = repository.get_statuses(
        (Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),)
    )

    assert statuses == {
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"): ReplyDraftStatus.EDITED
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
            case_id, subject, body, status, model_name, operator_instruction, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "Temat",
            "Tresc",
            "broken",
            "qwen3:4b",
            None,
            "2026-07-23T10:00:00+00:00",
            "2026-07-23T10:00:00+00:00",
        ),
    )
    repository._connection.commit()

    with pytest.raises(RuntimeError, match="unknown status"):
        repository.get(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    repository.close()
