from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aioffice.application import ImportedMailConflictError
from aioffice.domain import Identifier
from aioffice.infrastructure import SQLiteImportedMailRepository


def test_has_imported_returns_false_before_save(tmp_path: Path) -> None:
    repository = SQLiteImportedMailRepository(database_path=tmp_path / "storage" / "aioffice.db")

    assert repository.has_imported("imap.example.com/user/INBOX", "1") is False
    repository.close()


def test_has_imported_returns_true_after_save(tmp_path: Path) -> None:
    repository = SQLiteImportedMailRepository(database_path=tmp_path / "storage" / "aioffice.db")
    repository.save_import(
        mailbox_identity="imap.example.com/user/INBOX",
        uid="1",
        message_id="<one@example.com>",
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    assert repository.has_imported("imap.example.com/user/INBOX", "1") is True
    repository.close()


def test_same_uid_in_different_mailbox_identity_is_allowed(tmp_path: Path) -> None:
    repository = SQLiteImportedMailRepository(database_path=tmp_path / "storage" / "aioffice.db")
    repository.save_import(
        mailbox_identity="imap.example.com/user/INBOX",
        uid="1",
        message_id="<one@example.com>",
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )
    repository.save_import(
        mailbox_identity="imap.example.com/user/Sales",
        uid="1",
        message_id="<two@example.com>",
        case_id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )

    assert repository.has_imported("imap.example.com/user/INBOX", "1") is True
    assert repository.has_imported("imap.example.com/user/Sales", "1") is True
    repository.close()


def test_same_uid_in_same_mailbox_raises_conflict(tmp_path: Path) -> None:
    repository = SQLiteImportedMailRepository(database_path=tmp_path / "storage" / "aioffice.db")
    repository.save_import(
        mailbox_identity="imap.example.com/user/INBOX",
        uid="1",
        message_id="<one@example.com>",
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    with pytest.raises(ImportedMailConflictError):
        repository.save_import(
            mailbox_identity="imap.example.com/user/INBOX",
            uid="1",
            message_id="<two@example.com>",
            case_id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        )

    repository.close()


def test_message_id_none_is_allowed(tmp_path: Path) -> None:
    repository = SQLiteImportedMailRepository(database_path=tmp_path / "storage" / "aioffice.db")

    repository.save_import(
        mailbox_identity="imap.example.com/user/INBOX",
        uid="1",
        message_id=None,
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    assert repository.has_imported("imap.example.com/user/INBOX", "1") is True
    repository.close()


def test_connection_does_not_remain_in_open_transaction_after_conflict(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "aioffice.db"
    repository = SQLiteImportedMailRepository(database_path=database_path)
    repository.save_import(
        mailbox_identity="imap.example.com/user/INBOX",
        uid="1",
        message_id="<one@example.com>",
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    with pytest.raises(ImportedMailConflictError):
        repository.save_import(
            mailbox_identity="imap.example.com/user/INBOX",
            uid="1",
            message_id="<two@example.com>",
            case_id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        )

    repository.save_import(
        mailbox_identity="imap.example.com/user/INBOX",
        uid="2",
        message_id="<three@example.com>",
        case_id=Identifier.from_string("cccccccc-cccc-cccc-cccc-cccccccccccc"),
    )

    connection = sqlite3.connect(database_path)
    count = connection.execute("SELECT COUNT(*) FROM imported_mail").fetchone()[0]
    connection.close()

    assert count == 2
    repository.close()
