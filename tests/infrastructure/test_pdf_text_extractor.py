from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
import pymupdf

from aioffice.application import DocumentExtractionError, DownloadableArtifact
from aioffice.domain import ArtifactType, Identifier, StorageReference
from aioffice.infrastructure import PDFTextExtractor


def _artifact(
    display_name: str = "document.pdf",
    content_type: str | None = "application/pdf",
) -> DownloadableArtifact:
    return DownloadableArtifact(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        position=0,
        artifact_type=ArtifactType.ATTACHMENT,
        storage_reference=StorageReference(
            storage_name="filesystem",
            locator="artifacts/aa/bb/document.pdf",
        ),
        display_name=display_name,
        content_type=content_type,
    )


def _pdf_bytes(*page_texts: str) -> bytes:
    document = pymupdf.open()
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    for page_text in page_texts:
        page = document.new_page()
        if page_text:
            if font_path.exists():
                page.insert_text((72, 72), page_text, fontname="arial", fontfile=str(font_path))
            else:
                page.insert_text((72, 72), page_text)
    try:
        return document.tobytes()
    finally:
        document.close()


def test_pdf_text_extractor_supports_pdf_content_type_and_extension() -> None:
    extractor = PDFTextExtractor()

    assert extractor.supports(_artifact())
    assert extractor.supports(_artifact(display_name="document.PDF", content_type=None))


def test_pdf_text_extractor_supports_pdf_locator_even_when_metadata_is_generic() -> None:
    extractor = PDFTextExtractor()
    artifact = DownloadableArtifact(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        position=0,
        artifact_type=ArtifactType.ATTACHMENT,
        storage_reference=StorageReference(
            storage_name="filesystem",
            locator="artifacts/aa/bb/document.pdf",
        ),
        display_name="attachment.bin",
        content_type="application/octet-stream",
    )

    assert extractor.supports(artifact)


def test_pdf_text_extractor_extracts_single_page_text() -> None:
    extractor = PDFTextExtractor()

    result = extractor.extract_text(BytesIO(_pdf_bytes("Hello PDF")))

    assert result == "Hello PDF"


def test_pdf_text_extractor_extracts_multiple_pages_in_order() -> None:
    extractor = PDFTextExtractor()

    result = extractor.extract_text(BytesIO(_pdf_bytes("First page", "Second page")))

    assert result == "First page\n\nSecond page"


def test_pdf_text_extractor_returns_none_for_blank_pdf() -> None:
    extractor = PDFTextExtractor()

    result = extractor.extract_text(BytesIO(_pdf_bytes("")))

    assert result is None


def test_pdf_text_extractor_returns_none_for_pdf_without_text_layer() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.draw_rect((50, 50, 150, 150))
    pdf_bytes = document.tobytes()
    document.close()
    extractor = PDFTextExtractor()

    result = extractor.extract_text(BytesIO(pdf_bytes))

    assert result is None


def test_pdf_text_extractor_raises_controlled_error_for_corrupted_pdf() -> None:
    extractor = PDFTextExtractor()

    with pytest.raises(DocumentExtractionError, match="PDF text extraction failed"):
        extractor.extract_text(BytesIO(b"not a pdf"))


def test_pdf_text_extractor_preserves_polish_characters() -> None:
    extractor = PDFTextExtractor()

    result = extractor.extract_text(BytesIO(_pdf_bytes("Zażółć gęślą jaźń")))

    assert result == "Zażółć gęślą jaźń"
