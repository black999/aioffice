"""Application layer for AI Office."""

from .case_numbers import CaseNumberProvider, format_case_reference
from .cases import CaseFactory, InMemoryCaseRegistry
from .mail import (
    ImportedMailConflictError,
    ImportedMailRepository,
    MailboxClient,
    MailboxMessage,
    MailImportResult,
)
from .repositories import ArtifactLocatorConflictError, CaseRepository, PersistedCase
from .storage import DocumentStorage

__all__ = [
    "CaseFactory",
    "ArtifactLocatorConflictError",
    "CaseNumberProvider",
    "CaseRepository",
    "DocumentStorage",
    "ImportedMailConflictError",
    "ImportedMailRepository",
    "InMemoryCaseRegistry",
    "MailboxClient",
    "MailboxMessage",
    "MailImportResult",
    "PersistedCase",
    "format_case_reference",
]
