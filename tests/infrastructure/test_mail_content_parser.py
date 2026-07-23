from __future__ import annotations

from aioffice.infrastructure import StandardLibraryMailContentParser


def test_parser_extracts_plain_text_body() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Plain\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Hello\r\n\r\n\r\nWorld\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.body_text == "Hello\n\nWorld"
    assert parsed.attachments == ()


def test_parser_prefers_text_plain_in_multipart_alternative() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Alternative\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/alternative; boundary="alt"\r\n'
        b"\r\n"
        b"--alt\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Plain body\r\n"
        b"--alt\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<p>HTML body</p>\r\n"
        b"--alt--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.body_text == "Plain body"


def test_parser_falls_back_to_html() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Html\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<div>Hello<br>World</div>\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.body_text == "Hello\nWorld"


def test_parser_decodes_utf8_text() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        "From: sender@example.com\r\n"
        "Subject: UTF-8\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Zażółć gęślą jaźń\r\n"
    ).encode("utf-8")

    parsed = parser.parse(raw_message)

    assert parsed.body_text == "Zażółć gęślą jaźń"


def test_parser_decodes_iso_8859_2_text() -> None:
    parser = StandardLibraryMailContentParser()
    body = "Zażółć gęślą jaźń".encode("iso-8859-2")
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Latin2\r\n"
        b"Content-Type: text/plain; charset=iso-8859-2\r\n"
        b"Content-Transfer-Encoding: 8bit\r\n"
        b"\r\n"
        + body
        + b"\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.body_text == "Zażółć gęślą jaźń"


def test_parser_returns_none_when_body_is_missing() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Empty\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="mix"\r\n'
        b"\r\n"
        b"--mix\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment; filename=file.bin\r\n"
        b"\r\n"
        b"\x00\x01\x02\r\n"
        b"--mix--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.body_text is None


def test_parser_extracts_single_attachment() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Attachment\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="mix"\r\n'
        b"\r\n"
        b"--mix\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Body\r\n"
        b"--mix\r\n"
        b"Content-Type: application/pdf\r\n"
        b"Content-Disposition: attachment; filename=report.pdf\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"UERG\r\n"
        b"--mix--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.attachments[0].filename == "report.pdf"
    assert parsed.attachments[0].content_type == "application/pdf"
    assert parsed.attachments[0].payload == b"PDF"


def test_parser_extracts_multiple_attachments_in_order() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Attachments\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="mix"\r\n'
        b"\r\n"
        b"--mix\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Body\r\n"
        b"--mix\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment; filename=one.bin\r\n"
        b"\r\n"
        b"one\r\n"
        b"--mix\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment; filename=two.bin\r\n"
        b"\r\n"
        b"two\r\n"
        b"--mix--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert tuple(attachment.filename for attachment in parsed.attachments) == ("one.bin", "two.bin")


def test_parser_treats_inline_part_with_filename_as_attachment() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Inline\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/related; boundary="mix"\r\n'
        b"\r\n"
        b"--mix\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Body\r\n"
        b"--mix\r\n"
        b"Content-Type: image/png\r\n"
        b"Content-Disposition: inline; filename=logo.png\r\n"
        b"\r\n"
        b"PNG\r\n"
        b"--mix--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.attachments[0].filename == "logo.png"


def test_parser_ignores_multipart_container_as_attachment() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Nested\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="outer"\r\n'
        b"\r\n"
        b"--outer\r\n"
        b'Content-Type: multipart/alternative; boundary="inner"\r\n'
        b"\r\n"
        b"--inner\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Body\r\n"
        b"--inner--\r\n"
        b"--outer--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.body_text == "Body"
    assert parsed.attachments == ()


def test_parser_keeps_unicode_filename() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Unicode filename\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="mix"\r\n'
        b"\r\n"
        b"--mix\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment; filename*=utf-8''za%C5%82%C4%85cznik.txt\r\n"
        b"\r\n"
        b"payload\r\n"
        b"--mix--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.attachments[0].filename == "załącznik.txt"


def test_parser_allows_attachment_without_filename() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: No filename\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="mix"\r\n'
        b"\r\n"
        b"--mix\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment\r\n"
        b"\r\n"
        b"BIN\r\n"
        b"--mix--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.attachments[0].filename is None


def test_parser_keeps_binary_payload_unmodified() -> None:
    parser = StandardLibraryMailContentParser()
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Subject: Binary\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="mix"\r\n'
        b"\r\n"
        b"--mix\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment; filename=data.bin\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"AAEC/w==\r\n"
        b"--mix--\r\n"
    )

    parsed = parser.parse(raw_message)

    assert parsed.attachments[0].payload == b"\x00\x01\x02\xff"
