from __future__ import annotations

from io import BytesIO
import zipfile

import pytest

from aioffice.application import DocumentExtractionError, DownloadableArtifact
from aioffice.domain import ArtifactType, Identifier, StorageReference
from aioffice.infrastructure import DOCXTextExtractor


def _artifact(
    display_name: str = "document.docx",
    content_type: str | None = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
) -> DownloadableArtifact:
    return DownloadableArtifact(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        position=0,
        artifact_type=ArtifactType.ATTACHMENT,
        storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/document.docx"),
        display_name=display_name,
        content_type=content_type,
    )


def _docx_bytes(document_xml: str, *, extras: dict[str, bytes] | None = None) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )
        archive.writestr("word/document.xml", document_xml)
        if extras is not None:
            for name, payload in extras.items():
                archive.writestr(name, payload)
    return buffer.getvalue()


def test_docx_text_extractor_supports_docx_content_type_and_extension() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=1024)

    assert extractor.supports(_artifact())
    assert extractor.supports(_artifact(display_name="document.DOCX", content_type=None))


def test_docx_text_extractor_extracts_single_paragraph() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=1024)
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body></w:document>"
    )

    result = extractor.extract_text(BytesIO(_docx_bytes(xml)))

    assert result == "Hello DOCX"


def test_docx_text_extractor_extracts_multiple_paragraphs_and_table_text() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=4096)
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>First</w:t></w:r></w:p>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "<w:p><w:r><w:t>Second</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )

    result = extractor.extract_text(BytesIO(_docx_bytes(xml)))

    assert result == "First\n\nCell\n\nSecond"


def test_docx_text_extractor_preserves_polish_characters() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=1024)
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Zażółć gęślą jaźń</w:t></w:r></w:p></w:body></w:document>"
    )

    result = extractor.extract_text(BytesIO(_docx_bytes(xml)))

    assert result == "Zażółć gęślą jaźń"


def test_docx_text_extractor_returns_none_for_empty_document() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=1024)
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'

    result = extractor.extract_text(BytesIO(_docx_bytes(xml)))

    assert result is None


def test_docx_text_extractor_raises_controlled_error_for_bad_zip() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=1024)

    with pytest.raises(DocumentExtractionError, match="DOCX archive is invalid"):
        extractor.extract_text(BytesIO(b"not a zip"))


def test_docx_text_extractor_raises_controlled_error_when_document_xml_is_missing() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=1024)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "x")

    with pytest.raises(DocumentExtractionError, match="document.xml entry is missing"):
        extractor.extract_text(BytesIO(buffer.getvalue()))


def test_docx_text_extractor_respects_xml_size_limit() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=10)
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>"
    )

    with pytest.raises(DocumentExtractionError, match="exceeds extraction limit"):
        extractor.extract_text(BytesIO(_docx_bytes(xml)))


def test_docx_text_extractor_ignores_non_text_entries() -> None:
    extractor = DOCXTextExtractor(max_xml_bytes=4096)
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>"
    )

    result = extractor.extract_text(
        BytesIO(_docx_bytes(xml, extras={"word/media/image1.png": b"\x89PNG\r\n"}))
    )

    assert result == "Hello"
