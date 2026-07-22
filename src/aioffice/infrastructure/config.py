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

    @classmethod
    def from_environment(cls) -> AppSettings:
        """Build application settings from environment variables."""

        data_directory = Path(os.environ.get("AIOFFICE_DATA_DIR", "storage")).expanduser().resolve()
        host = os.environ.get("AIOFFICE_HOST", "127.0.0.1")
        port_raw = os.environ.get("AIOFFICE_PORT", "8000")
        try:
            port = int(port_raw)
        except ValueError as error:
            msg = f"AIOFFICE_PORT must be an integer, got {port_raw!r}"
            raise ValueError(msg) from error
        if not 1 <= port <= 65535:
            msg = f"AIOFFICE_PORT must be between 1 and 65535, got {port}"
            raise ValueError(msg)

        return cls(
            data_directory=data_directory,
            database_path=data_directory / "aioffice.db",
            artifacts_directory=data_directory / "artifacts",
            incoming_directory=data_directory / "incoming",
            processed_directory=data_directory / "processed",
            host=host,
            port=port,
        )
