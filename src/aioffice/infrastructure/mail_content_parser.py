"""Mail body and attachment parser backed by the Python standard library."""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.parser import BytesParser
from email.message import EmailMessage
from email.policy import default
from html import unescape

from aioffice.application import MailContentParser, ParsedAttachment, ParsedMailContent


_HTML_BREAK_PATTERN = re.compile(r"<\s*(br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>", re.IGNORECASE)
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_BLANK_LINE_PATTERN = re.compile(r"\n{3,}")


@dataclass(slots=True)
class StandardLibraryMailContentParser(MailContentParser):
    """Parse RFC 822 messages into normalized text and attachments."""

    def parse(self, raw_message: bytes) -> ParsedMailContent:
        message = BytesParser(policy=default).parsebytes(raw_message)
        plain_body: str | None = None
        html_body: str | None = None
        attachments: list[ParsedAttachment] = []

        for part in message.walk():
            if part.is_multipart():
                continue

            filename = part.get_filename()
            disposition = (part.get_content_disposition() or "").lower()
            content_type = part.get_content_type()

            if disposition == "attachment" or (disposition == "inline" and filename is not None):
                payload = part.get_payload(decode=True)
                attachments.append(
                    ParsedAttachment(
                        filename=filename,
                        content_type=content_type,
                        payload=payload if isinstance(payload, bytes) else b"",
                    )
                )
                continue

            if filename is not None:
                continue

            if content_type == "text/plain" and plain_body is None:
                plain_body = self._normalize_text(self._get_text_content(part))
            elif content_type == "text/html" and html_body is None:
                html_body = self._normalize_text(self._strip_html(self._get_text_content(part)))

        body_text = plain_body or html_body
        return ParsedMailContent(body_text=body_text, attachments=tuple(attachments))

    def _get_text_content(self, part: EmailMessage) -> str:
        content = part.get_content()
        if isinstance(content, str):
            return content
        if isinstance(content, bytes):
            return content.decode(part.get_content_charset() or "utf-8", errors="replace")
        return str(content)

    def _strip_html(self, html: str) -> str:
        with_line_breaks = _HTML_BREAK_PATTERN.sub("\n", html)
        without_tags = _HTML_TAG_PATTERN.sub("", with_line_breaks)
        return unescape(without_tags)

    def _normalize_text(self, text: str) -> str | None:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = _BLANK_LINE_PATTERN.sub("\n\n", normalized)
        if not normalized:
            return None
        return normalized
