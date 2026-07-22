"""Application service for document import."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aioffice.application.case_numbers import CaseNumberProvider
from aioffice.application.cases import CaseFactory
from aioffice.application.repositories import CaseRepository
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
        if self._has_storage_reference(storage_reference.locator):
            return None

        artifact = Artifact(artifact_type=ArtifactType.PDF, storage_reference=storage_reference)
        case = self.case_factory.create_from_artifact(artifact)
        reference_number = self.case_number_provider.next_number()
        self.case_repository.save(case, reference_number)
        return case

    def _has_storage_reference(self, locator: str) -> bool:
        return any(
            artifact.storage_reference.locator == locator
            for persisted_case in self.case_repository.list()
            for artifact in persisted_case.case.artifacts
        )
