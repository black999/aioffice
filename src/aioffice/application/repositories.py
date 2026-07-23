"""Repository interfaces for the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from aioffice.domain import Case, Identifier


class ArtifactLocatorConflictError(RuntimeError):
    """Raised when an artifact locator is already assigned to another case."""


@dataclass(frozen=True, slots=True)
class PersistedCase:
    """Case plus persistence metadata needed by the application layer."""

    case: Case
    reference_number: int
    status: str
    created_at: str


class CaseRepository(Protocol):
    """Persistence contract for cases."""

    def save(self, case: Case, reference_number: int) -> None:
        """Persist a case."""

    def get(self, case_id: Identifier) -> PersistedCase | None:
        """Load a case by identifier."""

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        """Load a case by its primary artifact locator."""

    def list(self) -> tuple[PersistedCase, ...]:
        """List all persisted cases."""

    def count(self) -> int:
        """Count all persisted cases."""
