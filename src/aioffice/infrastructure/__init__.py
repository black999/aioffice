"""Infrastructure layer for AI Office."""

from .classification_repository import SQLiteCaseClassificationRepository
from .config import AppSettings
from .docx_text_extractor import DOCXTextExtractor
from .imap_client import IMAPMailboxClient
from .imported_mail_repository import SQLiteImportedMailRepository
from .mail_poller import MailImportPoller, MailPollStatus
from .mail_content_parser import StandardLibraryMailContentParser
from .ollama_case_classifier import OllamaCaseClassifier
from .pdf_text_extractor import PDFTextExtractor
from .sqlite_repository import SQLiteCaseNumberProvider, SQLiteCaseRepository
from .storage import FilesystemStorage
from .watch_folder import WatchFolder

__all__ = [
    "AppSettings",
    "DOCXTextExtractor",
    "FilesystemStorage",
    "IMAPMailboxClient",
    "OllamaCaseClassifier",
    "StandardLibraryMailContentParser",
    "MailImportPoller",
    "MailPollStatus",
    "PDFTextExtractor",
    "SQLiteCaseClassificationRepository",
    "SQLiteCaseNumberProvider",
    "SQLiteCaseRepository",
    "SQLiteImportedMailRepository",
    "WatchFolder",
]
