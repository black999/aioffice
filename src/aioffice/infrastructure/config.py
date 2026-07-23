"""Centralized runtime configuration for AI Office."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Runtime settings derived from environment variables."""

    data_directory: Path
    database_path: Path
    artifacts_directory: Path
    incoming_directory: Path
    processed_directory: Path
    host: str
    port: int
    imap_host: str | None = None
    imap_port: int = 993
    imap_username: str | None = None
    imap_password: str | None = None
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    imap_polling_enabled: bool = False
    imap_polling_interval_seconds: int = 300
    imap_polling_run_immediately: bool = False
    imap_max_attachment_bytes: int = 25 * 1024 * 1024
    imap_max_attachments_per_message: int = 50
    document_extraction_max_input_bytes: int = 50 * 1024 * 1024
    document_extraction_max_output_chars: int = 2_000_000
    ai_classification_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout_seconds: int = 120
    ai_classification_max_input_chars: int = 100_000
    ai_reply_draft_enabled: bool = False
    reply_draft_model: str | None = None
    reply_draft_timeout_seconds: int = 180
    reply_draft_max_input_chars: int = 150_000
    reply_draft_max_operator_instruction_chars: int = 2000

    @classmethod
    def from_environment(cls) -> AppSettings:
        """Build application settings from environment variables."""

        data_directory = Path(os.environ.get("AIOFFICE_DATA_DIR", "storage")).expanduser().resolve()
        host = os.environ.get("AIOFFICE_HOST", "127.0.0.1")
        port_raw = os.environ.get("AIOFFICE_PORT", "8000")
        imap_host = os.environ.get("AIOFFICE_IMAP_HOST")
        imap_username = os.environ.get("AIOFFICE_IMAP_USERNAME")
        imap_password = os.environ.get("AIOFFICE_IMAP_PASSWORD")
        imap_mailbox = os.environ.get("AIOFFICE_IMAP_MAILBOX", "INBOX")
        imap_use_ssl_raw = os.environ.get("AIOFFICE_IMAP_USE_SSL", "true")
        imap_port_raw = os.environ.get("AIOFFICE_IMAP_PORT", "993")
        imap_polling_enabled_raw = os.environ.get("AIOFFICE_IMAP_POLLING_ENABLED", "false")
        imap_polling_interval_raw = os.environ.get("AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS", "300")
        imap_polling_run_immediately_raw = os.environ.get(
            "AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY",
            "false",
        )
        imap_max_attachment_bytes_raw = os.environ.get(
            "AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES",
            str(25 * 1024 * 1024),
        )
        imap_max_attachments_per_message_raw = os.environ.get(
            "AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE",
            "50",
        )
        document_extraction_max_input_bytes_raw = os.environ.get(
            "AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES",
            str(50 * 1024 * 1024),
        )
        document_extraction_max_output_chars_raw = os.environ.get(
            "AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS",
            "2000000",
        )
        ai_classification_enabled_raw = os.environ.get(
            "AIOFFICE_AI_CLASSIFICATION_ENABLED",
            "false",
        )
        ollama_base_url_raw = os.environ.get(
            "AIOFFICE_OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        )
        ollama_model_raw = os.environ.get("AIOFFICE_OLLAMA_MODEL", "qwen2.5:7b")
        ollama_timeout_seconds_raw = os.environ.get("AIOFFICE_OLLAMA_TIMEOUT_SECONDS", "120")
        ai_classification_max_input_chars_raw = os.environ.get(
            "AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS",
            "100000",
        )
        ai_reply_draft_enabled_raw = os.environ.get(
            "AIOFFICE_AI_REPLY_DRAFT_ENABLED",
            "false",
        )
        reply_draft_model_raw = os.environ.get("AIOFFICE_REPLY_DRAFT_MODEL")
        reply_draft_timeout_seconds_raw = os.environ.get(
            "AIOFFICE_REPLY_DRAFT_TIMEOUT_SECONDS",
            "180",
        )
        reply_draft_max_input_chars_raw = os.environ.get(
            "AIOFFICE_REPLY_DRAFT_MAX_INPUT_CHARS",
            "150000",
        )
        reply_draft_max_operator_instruction_chars_raw = os.environ.get(
            "AIOFFICE_REPLY_DRAFT_MAX_OPERATOR_INSTRUCTION_CHARS",
            "2000",
        )
        try:
            port = int(port_raw)
        except ValueError as error:
            msg = f"AIOFFICE_PORT must be an integer, got {port_raw!r}"
            raise ValueError(msg) from error
        if not 1 <= port <= 65535:
            msg = f"AIOFFICE_PORT must be between 1 and 65535, got {port}"
            raise ValueError(msg)
        try:
            imap_port = int(imap_port_raw)
        except ValueError as error:
            msg = f"AIOFFICE_IMAP_PORT must be an integer, got {imap_port_raw!r}"
            raise ValueError(msg) from error
        if not 1 <= imap_port <= 65535:
            msg = f"AIOFFICE_IMAP_PORT must be between 1 and 65535, got {imap_port}"
            raise ValueError(msg)

        normalized_imap_use_ssl = imap_use_ssl_raw.strip().lower()
        if normalized_imap_use_ssl not in {"true", "false"}:
            msg = f"AIOFFICE_IMAP_USE_SSL must be 'true' or 'false', got {imap_use_ssl_raw!r}"
            raise ValueError(msg)
        imap_use_ssl = normalized_imap_use_ssl == "true"
        imap_polling_enabled = _parse_boolean(
            "AIOFFICE_IMAP_POLLING_ENABLED",
            imap_polling_enabled_raw,
        )
        imap_polling_run_immediately = _parse_boolean(
            "AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY",
            imap_polling_run_immediately_raw,
        )
        try:
            imap_polling_interval_seconds = int(imap_polling_interval_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS must be an integer, "
                f"got {imap_polling_interval_raw!r}"
            )
            raise ValueError(msg) from error
        if not 30 <= imap_polling_interval_seconds <= 86400:
            msg = (
                "AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS must be between 30 and 86400, "
                f"got {imap_polling_interval_seconds}"
            )
            raise ValueError(msg)
        try:
            imap_max_attachment_bytes = int(imap_max_attachment_bytes_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES must be an integer, "
                f"got {imap_max_attachment_bytes_raw!r}"
            )
            raise ValueError(msg) from error
        if not 1024 * 1024 <= imap_max_attachment_bytes <= 100 * 1024 * 1024:
            msg = (
                "AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES must be between 1048576 and 104857600, "
                f"got {imap_max_attachment_bytes}"
            )
            raise ValueError(msg)
        try:
            imap_max_attachments_per_message = int(imap_max_attachments_per_message_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE must be an integer, "
                f"got {imap_max_attachments_per_message_raw!r}"
            )
            raise ValueError(msg) from error
        if not 1 <= imap_max_attachments_per_message <= 200:
            msg = (
                "AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE must be between 1 and 200, "
                f"got {imap_max_attachments_per_message}"
            )
            raise ValueError(msg)
        try:
            document_extraction_max_input_bytes = int(document_extraction_max_input_bytes_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES must be an integer, "
                f"got {document_extraction_max_input_bytes_raw!r}"
            )
            raise ValueError(msg) from error
        if not 1024 * 1024 <= document_extraction_max_input_bytes <= 200 * 1024 * 1024:
            msg = (
                "AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES must be between 1048576 and 209715200, "
                f"got {document_extraction_max_input_bytes}"
            )
            raise ValueError(msg)
        try:
            document_extraction_max_output_chars = int(document_extraction_max_output_chars_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS must be an integer, "
                f"got {document_extraction_max_output_chars_raw!r}"
            )
            raise ValueError(msg) from error
        if not 10_000 <= document_extraction_max_output_chars <= 10_000_000:
            msg = (
                "AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS must be between 10000 and 10000000, "
                f"got {document_extraction_max_output_chars}"
            )
            raise ValueError(msg)
        ai_classification_enabled = _parse_boolean(
            "AIOFFICE_AI_CLASSIFICATION_ENABLED",
            ai_classification_enabled_raw,
        )
        ollama_base_url = ollama_base_url_raw.strip().rstrip("/")
        if not ollama_base_url.startswith(("http://", "https://")):
            msg = "AIOFFICE_OLLAMA_BASE_URL must start with 'http://' or 'https://'"
            raise ValueError(msg)
        ollama_model = ollama_model_raw.strip()
        if not ollama_model:
            msg = "AIOFFICE_OLLAMA_MODEL must not be empty"
            raise ValueError(msg)
        try:
            ollama_timeout_seconds = int(ollama_timeout_seconds_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_OLLAMA_TIMEOUT_SECONDS must be an integer, "
                f"got {ollama_timeout_seconds_raw!r}"
            )
            raise ValueError(msg) from error
        if not 5 <= ollama_timeout_seconds <= 600:
            msg = (
                "AIOFFICE_OLLAMA_TIMEOUT_SECONDS must be between 5 and 600, "
                f"got {ollama_timeout_seconds}"
            )
            raise ValueError(msg)
        try:
            ai_classification_max_input_chars = int(ai_classification_max_input_chars_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS must be an integer, "
                f"got {ai_classification_max_input_chars_raw!r}"
            )
            raise ValueError(msg) from error
        if not 10_000 <= ai_classification_max_input_chars <= 1_000_000:
            msg = (
                "AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS must be between 10000 and 1000000, "
                f"got {ai_classification_max_input_chars}"
            )
            raise ValueError(msg)
        ai_reply_draft_enabled = _parse_boolean(
            "AIOFFICE_AI_REPLY_DRAFT_ENABLED",
            ai_reply_draft_enabled_raw,
        )
        reply_draft_model = (
            reply_draft_model_raw.strip()
            if reply_draft_model_raw is not None
            else ollama_model
        )
        if not reply_draft_model:
            reply_draft_model = ollama_model
        if ai_reply_draft_enabled and not reply_draft_model:
            msg = "AIOFFICE_REPLY_DRAFT_MODEL must not be empty when reply drafts are enabled"
            raise ValueError(msg)
        try:
            reply_draft_timeout_seconds = int(reply_draft_timeout_seconds_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_REPLY_DRAFT_TIMEOUT_SECONDS must be an integer, "
                f"got {reply_draft_timeout_seconds_raw!r}"
            )
            raise ValueError(msg) from error
        if not 5 <= reply_draft_timeout_seconds <= 600:
            msg = (
                "AIOFFICE_REPLY_DRAFT_TIMEOUT_SECONDS must be between 5 and 600, "
                f"got {reply_draft_timeout_seconds}"
            )
            raise ValueError(msg)
        try:
            reply_draft_max_input_chars = int(reply_draft_max_input_chars_raw)
        except ValueError as error:
            msg = (
                "AIOFFICE_REPLY_DRAFT_MAX_INPUT_CHARS must be an integer, "
                f"got {reply_draft_max_input_chars_raw!r}"
            )
            raise ValueError(msg) from error
        if not 10_000 <= reply_draft_max_input_chars <= 1_000_000:
            msg = (
                "AIOFFICE_REPLY_DRAFT_MAX_INPUT_CHARS must be between 10000 and 1000000, "
                f"got {reply_draft_max_input_chars}"
            )
            raise ValueError(msg)
        try:
            reply_draft_max_operator_instruction_chars = int(
                reply_draft_max_operator_instruction_chars_raw
            )
        except ValueError as error:
            msg = (
                "AIOFFICE_REPLY_DRAFT_MAX_OPERATOR_INSTRUCTION_CHARS must be an integer, "
                f"got {reply_draft_max_operator_instruction_chars_raw!r}"
            )
            raise ValueError(msg) from error
        if not 100 <= reply_draft_max_operator_instruction_chars <= 10_000:
            msg = (
                "AIOFFICE_REPLY_DRAFT_MAX_OPERATOR_INSTRUCTION_CHARS must be between 100 and 10000, "
                f"got {reply_draft_max_operator_instruction_chars}"
            )
            raise ValueError(msg)

        return cls(
            data_directory=data_directory,
            database_path=data_directory / "aioffice.db",
            artifacts_directory=data_directory / "artifacts",
            incoming_directory=data_directory / "incoming",
            processed_directory=data_directory / "processed",
            host=host,
            port=port,
            imap_host=imap_host,
            imap_port=imap_port,
            imap_username=imap_username,
            imap_password=imap_password,
            imap_mailbox=imap_mailbox,
            imap_use_ssl=imap_use_ssl,
            imap_polling_enabled=imap_polling_enabled,
            imap_polling_interval_seconds=imap_polling_interval_seconds,
            imap_polling_run_immediately=imap_polling_run_immediately,
            imap_max_attachment_bytes=imap_max_attachment_bytes,
            imap_max_attachments_per_message=imap_max_attachments_per_message,
            document_extraction_max_input_bytes=document_extraction_max_input_bytes,
            document_extraction_max_output_chars=document_extraction_max_output_chars,
            ai_classification_enabled=ai_classification_enabled,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
            ollama_timeout_seconds=ollama_timeout_seconds,
            ai_classification_max_input_chars=ai_classification_max_input_chars,
            ai_reply_draft_enabled=ai_reply_draft_enabled,
            reply_draft_model=reply_draft_model or None,
            reply_draft_timeout_seconds=reply_draft_timeout_seconds,
            reply_draft_max_input_chars=reply_draft_max_input_chars,
            reply_draft_max_operator_instruction_chars=reply_draft_max_operator_instruction_chars,
        )


def _parse_boolean(variable_name: str, raw_value: str) -> bool:
    normalized_value = raw_value.strip().lower()
    if normalized_value not in {"true", "false"}:
        msg = f"{variable_name} must be 'true' or 'false', got {raw_value!r}"
        raise ValueError(msg)
    return normalized_value == "true"
