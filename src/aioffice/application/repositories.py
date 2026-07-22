"""Repository interfaces for the application layer."""

from __future__ import annotations

from typing import Protocol

from aioffice.domain import Case, Identifier


class CaseRepository(Protocol):
    """Persistence contract for cases."""

    def save(self, case: Case) -> None:
        """Persist a case."""

    def get(self, case_id: Identifier) -> Case | None:
        """Load a case by identifier."""

    def list(self) -> tuple[Case, ...]:
        """List all persisted cases."""

    def count(self) -> int:
        """Count all persisted cases."""
