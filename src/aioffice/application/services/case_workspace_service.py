"""Read-only application service for the case workspace."""

from __future__ import annotations

from typing import BinaryIO
from dataclasses import dataclass

from aioffice.application import ArtifactRecord, CaseRepository, DownloadableArtifact
from aioffice.application.case_numbers import format_case_reference
from aioffice.application.storage import ArtifactNotFoundError, ArtifactStorageReader, UnsupportedStorageError
from aioffice.domain import ArtifactType, Identifier


@dataclass(frozen=True, slots=True)
class ArtifactSummary:
    """Minimal artifact data for the case workspace view."""

    position: int
    artifact_type: str
    storage_name: str
    locator: str
    display_name: str
    content_type: str | None
    download_url: str
    source_position: int | None
    is_truncated: bool


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
    email_body: str | None
    email_body_truncated: bool
    email_body_error: bool
    extraction_message: str | None
    artifacts: tuple[ArtifactSummary, ...]
    history: tuple[HistoryEntry, ...]


@dataclass(slots=True)
class CaseWorkspaceService:
    """Provide read-only case workspace data for the web layer."""

    repository: CaseRepository
    storage_reader: ArtifactStorageReader
    email_body_max_bytes: int = 1024 * 1024

    def get_case_workspace(
        self,
        case_id: str,
        *,
        extraction_message: str | None = None,
    ) -> CaseWorkspace | None:
        """Return the workspace read model for a case UUID."""

        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            return None

        persisted_case = self.repository.get(identifier)
        if persisted_case is None:
            return None

        email_body, email_body_truncated, email_body_error = self._load_email_body(
            persisted_case.artifact_records
        )
        artifacts = tuple(
            ArtifactSummary(
                position=position,
                artifact_type=record.artifact.artifact_type.value.upper(),
                storage_name=record.artifact.storage_reference.storage_name,
                locator=record.artifact.storage_reference.locator,
                display_name=record.display_name,
                content_type=record.content_type,
                download_url=f"/cases/{persisted_case.case.id}/artifacts/{position}/download",
                source_position=record.source_position,
                is_truncated=record.is_truncated,
            )
            for position, record in enumerate(persisted_case.artifact_records)
        )
        history = (
            HistoryEntry(title="Imported", timestamp=persisted_case.created_at),
        )
        return CaseWorkspace(
            case_id=str(persisted_case.case.id),
            case_reference=format_case_reference(persisted_case.reference_number),
            status=persisted_case.status,
            created_at=persisted_case.created_at,
            email_body=email_body,
            email_body_truncated=email_body_truncated,
            email_body_error=email_body_error,
            extraction_message=extraction_message,
            artifacts=artifacts,
            history=history,
        )

    def _load_email_body(
        self,
        artifact_records: tuple[ArtifactRecord, ...],
    ) -> tuple[str | None, bool, bool]:
        text_record: ArtifactRecord | None = None
        for record in artifact_records:
            if record.artifact.artifact_type is ArtifactType.TEXT and record.source_position is None:
                text_record = record
                break

        if text_record is None:
            return None, False, False

        try:
            with self.storage_reader.open_artifact(text_record.artifact.storage_reference) as handle:
                content = handle.read(self.email_body_max_bytes + 1)
        except (ArtifactNotFoundError, UnsupportedStorageError, OSError):
            return None, False, True

        truncated = len(content) > self.email_body_max_bytes
        content = content[: self.email_body_max_bytes]
        return content.decode("utf-8", errors="replace"), truncated, False


@dataclass(slots=True)
class ArtifactDownloadService:
    """Resolve a case artifact for safe download."""

    repository: CaseRepository
    storage_reader: ArtifactStorageReader

    def open_artifact(self, case_id: str, position: int) -> tuple[DownloadableArtifact, BinaryIO] | None:
        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            return None

        if position < 0:
            return None

        artifact = self.repository.get_artifact(identifier, position)
        if artifact is None:
            return None

        return artifact, self.storage_reader.open_artifact(artifact.storage_reference)
