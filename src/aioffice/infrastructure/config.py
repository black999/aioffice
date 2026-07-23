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
        )
