"""Document text extraction contracts for the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol

from .artifact_metadata import DownloadableArtifact


class DocumentExtractionError(RuntimeError):
    """Raised when text extraction from a document fails."""


class DocumentTextExtractor(Protocol):
    """Application-facing contract for extracting text from supported documents."""

    def supports(self, artifact: DownloadableArtifact) -> bool:
        """Return whether this extractor can handle the given artifact."""

    def extract_text(self, source: BinaryIO) -> str | None:
        """Extract text from an already opened document stream."""


@dataclass(frozen=True, slots=True)
class ExtractedDocumentText:
    """Normalized extracted text ready to be stored as a TEXT artifact."""

    source_position: int
    source_display_name: str
    text: str
    output_display_name: str
    is_truncated: bool = False


@dataclass(frozen=True, slots=True)
class DocumentExtractionResult:
    """Outcome of a manual document extraction run for one case."""

    extracted: int
    skipped: int
    failed: int
