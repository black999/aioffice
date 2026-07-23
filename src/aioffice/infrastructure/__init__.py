"""Infrastructure layer for AI Office."""

from .config import AppSettings
from .docx_text_extractor import DOCXTextExtractor
from .imap_client import IMAPMailboxClient
from .imported_mail_repository import SQLiteImportedMailRepository
from .mail_poller import MailImportPoller, MailPollStatus
from .mail_content_parser import StandardLibraryMailContentParser
from .pdf_text_extractor import PDFTextExtractor
from .sqlite_repository import SQLiteCaseNumberProvider, SQLiteCaseRepository
from .storage import FilesystemStorage
from .watch_folder import WatchFolder

__all__ = [
    "AppSettings",
    "DOCXTextExtractor",
    "FilesystemStorage",
    "IMAPMailboxClient",
    "StandardLibraryMailContentParser",
    "MailImportPoller",
    "MailPollStatus",
    "PDFTextExtractor",
    "SQLiteCaseNumberProvider",
    "SQLiteCaseRepository",
    "SQLiteImportedMailRepository",
    "WatchFolder",
]
