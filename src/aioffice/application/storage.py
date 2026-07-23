"""Storage abstractions for the application layer."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from typing import Protocol

from aioffice.domain import StorageReference


class ArtifactNotFoundError(RuntimeError):
    """Raised when an artifact cannot be found in storage."""


class UnsupportedStorageError(RuntimeError):
    """Raised when a storage provider cannot handle the given reference."""


class DocumentStorage(Protocol):
    """Application-facing storage contract for document import."""

    def store_file(self, source_path: Path) -> StorageReference:
        """Store a file and return its storage reference."""


class ArtifactStorageReader(Protocol):
    """Application-facing storage contract for reading persisted artifacts."""

    def open_artifact(self, storage_reference: StorageReference) -> BinaryIO:
        """Open an artifact for binary reading."""

    def get_artifact_size(self, storage_reference: StorageReference) -> int:
        """Return the artifact size in bytes."""
