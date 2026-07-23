"""Application layer for AI Office."""

from .artifact_metadata import ArtifactRecord, DownloadableArtifact, ensure_unique_display_name, sanitize_display_name
from .classification import (
    MAX_CLASSIFICATION_RATIONALE_CHARS,
    CaseCategory,
    CaseClassification,
    CaseClassificationError,
    CaseClassificationRepository,
    CaseClassificationResponseError,
    CaseClassificationResult,
    CaseClassifier,
    PersistedCaseClassification,
    build_persisted_case_classification,
    format_case_category_label,
    format_confidence_percent,
    normalize_rationale,
)
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
    "build_persisted_case_classification",
    "CaseCategory",
    "CaseClassification",
    "CaseClassificationError",
    "CaseClassificationRepository",
    "CaseClassificationResponseError",
    "CaseClassificationResult",
    "CaseClassifier",
    "CaseNumberProvider",
    "CaseRepository",
    "DocumentStorage",
    "DocumentExtractionError",
    "DocumentExtractionResult",
    "DocumentTextExtractor",
    "DownloadableArtifact",
    "ExtractedDocumentText",
    "format_case_category_label",
    "format_confidence_percent",
    "MailContentParser",
    "MAX_CLASSIFICATION_RATIONALE_CHARS",
    "ImportedMailConflictError",
    "ImportedMailRepository",
    "InMemoryCaseRegistry",
    "MailboxClient",
    "MailboxMessage",
    "MailImportResult",
    "ParsedAttachment",
    "ParsedMailContent",
    "PersistedCase",
    "PersistedCaseClassification",
    "ensure_unique_display_name",
    "format_case_reference",
    "normalize_rationale",
    "sanitize_display_name",
]
