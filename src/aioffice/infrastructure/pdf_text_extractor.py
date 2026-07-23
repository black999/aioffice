"""PDF text extraction using PyMuPDF."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import BinaryIO
from typing import Any

import pymupdf

from aioffice.application import DocumentExtractionError, DocumentTextExtractor, DownloadableArtifact


_BLANK_LINE_PATTERN = re.compile(r"\n{3,}")


def _normalize_text(value: str) -> str | None:
    normalized = value.replace("\xa0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _BLANK_LINE_PATTERN.sub("\n\n", normalized)
    normalized = normalized.strip()
    if not normalized:
        return None
    return normalized


@dataclass(frozen=True, slots=True)
class PDFTextExtractor(DocumentTextExtractor):
    """Extract text from PDFs that already contain a text layer."""

    def supports(self, artifact: DownloadableArtifact) -> bool:
        if artifact.content_type == "application/pdf":
            return True
        return artifact.display_name.lower().endswith(".pdf")

    def extract_text(self, source: BinaryIO) -> str | None:
        try:
            document: Any = pymupdf.open(stream=source.read(), filetype="pdf")  # type: ignore[no-untyped-call]
        except Exception as error:
            msg = "PDF text extraction failed"
            raise DocumentExtractionError(msg) from error

        try:
            pages = [document.load_page(index).get_text("text") for index in range(document.page_count)]
        except Exception as error:
            msg = "PDF text extraction failed"
            raise DocumentExtractionError(msg) from error
        finally:
            document.close()

        return _normalize_text("\n\n".join(pages))
