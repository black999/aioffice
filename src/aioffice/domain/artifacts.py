"""Artifact entities for the domain layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from .identifiers import Identifier
from .storage import StorageReference


class ArtifactType(StrEnum):
    """Supported artifact categories in Sprint 2."""

    ATTACHMENT = "attachment"
    EMAIL = "email"
    PDF = "pdf"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class Artifact:
    """Primary business object handled by the platform."""

    artifact_type: ArtifactType
    storage_reference: StorageReference
    id: Identifier = field(default_factory=Identifier.new)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            msg = "created_at must be timezone-aware"
            raise ValueError(msg)
