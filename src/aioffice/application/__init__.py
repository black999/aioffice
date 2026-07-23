"""Application layer for AI Office."""

from .artifact_metadata import ArtifactRecord, DownloadableArtifact, ensure_unique_display_name, sanitize_display_name
from .case_numbers import CaseNumberProvider, format_case_reference
from .cases import CaseFactory, InMemoryCaseRegistry
from .document_extraction import (
    DocumentExtractionError,
    DocumentExtractionResult,
    DocumentTextExtractor,
    ExtractedDocumentText,
)
from .mail import (
    ImportedMailConflictError,
    ImportedMailRepository,
    MailContentParser,
    MailboxClient,
    MailboxMessage,
    MailImportResult,
    ParsedAttachment,
    ParsedMailContent,
)
from .repositories import ArtifactLocatorConflictError, CaseRepository, PersistedCase
from .storage import ArtifactStorageReader, DocumentStorage

__all__ = [
    "CaseFactory",
    "ArtifactLocatorConflictError",
    "ArtifactRecord",
    "ArtifactStorageReader",
    "CaseNumberProvider",
    "CaseRepository",
    "DocumentStorage",
    "DocumentExtractionError",
    "DocumentExtractionResult",
    "DocumentTextExtractor",
    "DownloadableArtifact",
    "ExtractedDocumentText",
    "MailContentParser",
    "ImportedMailConflictError",
    "ImportedMailRepository",
    "InMemoryCaseRegistry",
    "MailboxClient",
    "MailboxMessage",
    "MailImportResult",
    "ParsedAttachment",
    "ParsedMailContent",
    "PersistedCase",
    "ensure_unique_display_name",
    "format_case_reference",
    "sanitize_display_name",
]
