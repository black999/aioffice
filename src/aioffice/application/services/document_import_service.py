"""Application service for document import."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aioffice.application import ArtifactRecord, sanitize_display_name
from aioffice.application.case_numbers import CaseNumberProvider
from aioffice.application.cases import CaseFactory
from aioffice.application.repositories import ArtifactLocatorConflictError, CaseRepository
from aioffice.application.storage import DocumentStorage
from aioffice.domain import Artifact, ArtifactType, Case


@dataclass(slots=True)
class DocumentImportService:
    """Import a document into the case workflow."""

    storage: DocumentStorage
    case_factory: CaseFactory
    case_repository: CaseRepository
    case_number_provider: CaseNumberProvider

    def import_pdf(self, source_path: Path) -> Case | None:
        """Store a PDF, create a case, and persist it if it is new."""

        storage_reference = self.storage.store_file(source_path)
        existing_case = self.case_repository.get_by_artifact_locator(storage_reference.locator)
        if existing_case is not None:
            return existing_case.case

        artifact = Artifact(artifact_type=ArtifactType.PDF, storage_reference=storage_reference)
        reference_number = self.case_number_provider.next_number()
        case = self.case_factory.create_from_artifact(artifact)
        artifact_records = (
            ArtifactRecord(
                artifact=artifact,
                display_name=sanitize_display_name(source_path.name, fallback="document.pdf"),
                content_type="application/pdf",
            ),
        )
        try:
            self.case_repository.save(case, reference_number, artifact_records=artifact_records)
        except ArtifactLocatorConflictError:
            existing_case = self.case_repository.get_by_artifact_locator(storage_reference.locator)
            if existing_case is None:
                raise
            return existing_case.case
        return case
