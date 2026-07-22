"""Storage abstractions for the application layer."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from aioffice.domain import StorageReference


class DocumentStorage(Protocol):
    """Application-facing storage contract for document import."""

    def store_file(self, source_path: Path) -> StorageReference:
        """Store a file and return its storage reference."""
