"""Mail import contracts for the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from aioffice.domain import Identifier


class ImportedMailConflictError(RuntimeError):
    """Raised when a mail import record already exists for a mailbox UID."""


@dataclass(frozen=True, slots=True)
class MailboxMessage:
    """Mailbox message data detached from any IMAP client implementation."""

    mailbox_identity: str
    uid: str
    message_id: str | None
    subject: str | None
    sender: str | None
    received_at: datetime | None
    raw_message: bytes


@dataclass(frozen=True, slots=True)
class MailImportResult:
    """Outcome of a single import run."""

    imported: int
    skipped: int
    failed: int


class MailboxClient(Protocol):
    """Application-facing mailbox client contract."""

    def list_messages(self) -> tuple[MailboxMessage, ...]:
        """Return messages available in the configured mailbox."""


class ImportedMailRepository(Protocol):
    """Persistence contract for imported mailbox messages."""

    def has_imported(self, mailbox_identity: str, uid: str) -> bool:
        """Return whether a mailbox UID has already been imported."""

    def save_import(
        self,
        mailbox_identity: str,
        uid: str,
        message_id: str | None,
        case_id: Identifier,
    ) -> None:
        """Persist a mailbox import record."""
