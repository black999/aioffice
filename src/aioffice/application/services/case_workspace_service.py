"""Read-only application service for the case workspace."""

from __future__ import annotations

from dataclasses import dataclass

from aioffice.application import CaseRepository
from aioffice.application.case_numbers import format_case_reference
from aioffice.domain import Identifier


@dataclass(frozen=True, slots=True)
class ArtifactSummary:
    """Minimal artifact data for the case workspace view."""

    artifact_type: str
    locator: str


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """Minimal history entry for the case workspace view."""

    title: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class CaseWorkspace:
    """Read model for the case workspace view."""

    case_id: str
    case_reference: str
    status: str
    created_at: str
    artifacts: tuple[ArtifactSummary, ...]
    history: tuple[HistoryEntry, ...]


@dataclass(slots=True)
class CaseWorkspaceService:
    """Provide read-only case workspace data for the web layer."""

    repository: CaseRepository

    def get_case_workspace(self, case_id: str) -> CaseWorkspace | None:
        """Return the workspace read model for a case UUID."""

        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            return None

        persisted_case = self.repository.get(identifier)
        if persisted_case is None:
            return None

        artifacts = tuple(
            ArtifactSummary(
                artifact_type=artifact.artifact_type.value.upper(),
                locator=artifact.storage_reference.locator,
            )
            for artifact in persisted_case.case.artifacts
        )
        history = (
            HistoryEntry(title="Imported", timestamp=persisted_case.created_at),
        )
        return CaseWorkspace(
            case_id=str(persisted_case.case.id),
            case_reference=format_case_reference(persisted_case.reference_number),
            status=persisted_case.status,
            created_at=persisted_case.created_at,
            artifacts=artifacts,
            history=history,
        )
