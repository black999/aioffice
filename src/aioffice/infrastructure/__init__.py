"""Infrastructure layer for AI Office."""

from .config import AppSettings
from .imap_client import IMAPMailboxClient
from .imported_mail_repository import SQLiteImportedMailRepository
from .mail_poller import MailImportPoller, MailPollStatus
from .mail_content_parser import StandardLibraryMailContentParser
from .sqlite_repository import SQLiteCaseNumberProvider, SQLiteCaseRepository
from .storage import FilesystemStorage
from .watch_folder import WatchFolder

__all__ = [
    "AppSettings",
    "FilesystemStorage",
    "IMAPMailboxClient",
    "StandardLibraryMailContentParser",
    "MailImportPoller",
    "MailPollStatus",
    "SQLiteCaseNumberProvider",
    "SQLiteCaseRepository",
    "SQLiteImportedMailRepository",
    "WatchFolder",
]
