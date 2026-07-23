"""DOCX text extraction using the standard library."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import BinaryIO

from aioffice.application import DocumentExtractionError, DocumentTextExtractor, DownloadableArtifact


_WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_BLANK_LINE_PATTERN = re.compile(r"\n{3,}")


def _normalize_text(value: str) -> str | None:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _BLANK_LINE_PATTERN.sub("\n\n", normalized)
    normalized = normalized.strip()
    if not normalized:
        return None
    return normalized


@dataclass(frozen=True, slots=True)
class DOCXTextExtractor(DocumentTextExtractor):
    """Extract text from DOCX files without unpacking them to disk."""

    max_xml_bytes: int

    def supports(self, artifact: DownloadableArtifact) -> bool:
        if (
            artifact.content_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            return True
        return artifact.display_name.lower().endswith(".docx")

    def extract_text(self, source: BinaryIO) -> str | None:
        try:
            with zipfile.ZipFile(source) as archive:
                try:
                    info = archive.getinfo("word/document.xml")
                except KeyError as error:
                    msg = "DOCX document.xml entry is missing"
                    raise DocumentExtractionError(msg) from error
                if info.file_size > self.max_xml_bytes:
                    msg = "DOCX document.xml exceeds extraction limit"
                    raise DocumentExtractionError(msg)
                xml_bytes = archive.read(info)
        except DocumentExtractionError:
            raise
        except zipfile.BadZipFile as error:
            msg = "DOCX archive is invalid"
            raise DocumentExtractionError(msg) from error
        except Exception as error:
            msg = "DOCX text extraction failed"
            raise DocumentExtractionError(msg) from error

        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as error:
            msg = "DOCX XML parsing failed"
            raise DocumentExtractionError(msg) from error

        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", _WORD_NAMESPACE):
            texts = [
                text_node.text or ""
                for text_node in paragraph.findall(".//w:t", _WORD_NAMESPACE)
            ]
            paragraph_text = "".join(texts).strip()
            if paragraph_text:
                paragraphs.append(paragraph_text)
        return _normalize_text("\n\n".join(paragraphs))
