"""Application service for manual AI case classification."""

from __future__ import annotations

from dataclasses import dataclass

from aioffice.application import (
    ArtifactRecord,
    ArtifactStorageReader,
    CaseClassificationRepository,
    CaseClassificationResult,
    CaseClassifier,
    CaseRepository,
    build_persisted_case_classification,
)
from aioffice.application.storage import ArtifactNotFoundError, UnsupportedStorageError
from aioffice.domain import ArtifactType, Identifier


@dataclass(slots=True)
class CaseClassificationService:
    """Classify a case from its persisted TEXT artifacts."""

    case_repository: CaseRepository
    classification_repository: CaseClassificationRepository
    storage_reader: ArtifactStorageReader
    classifier: CaseClassifier
    max_input_chars: int

    def classify_case(
        self,
        case_id: Identifier,
        *,
        force: bool = False,
    ) -> CaseClassificationResult | None:
        """Run manual classification for one case."""

        persisted_case = self.case_repository.get(case_id)
        if persisted_case is None:
            return None

        existing_classification = self.classification_repository.get(case_id)
        if existing_classification is not None and not force:
            return CaseClassificationResult(
                classification=existing_classification,
                skipped=True,
                reason="already_classified",
            )

        input_text = self._build_input_text(persisted_case.artifact_records)
        if input_text is None:
            return CaseClassificationResult(
                classification=existing_classification,
                skipped=True,
                reason="no_text",
            )

        classification = self.classifier.classify(input_text)
        persisted_classification = build_persisted_case_classification(
            case_id=case_id,
            classification=classification,
        )
        self.classification_repository.save(persisted_classification)
        return CaseClassificationResult(
            classification=persisted_classification,
            skipped=False,
            reason=None,
        )

    def _build_input_text(self, artifact_records: tuple[ArtifactRecord, ...]) -> str | None:
        sections: list[str] = []
        truncated = False
        for position, record in enumerate(artifact_records):
            if record.artifact.artifact_type is not ArtifactType.TEXT:
                continue
            try:
                with self.storage_reader.open_artifact(record.artifact.storage_reference) as handle:
                    text = handle.read().decode("utf-8", errors="replace").strip()
            except (ArtifactNotFoundError, UnsupportedStorageError, OSError, UnicodeError):
                continue
            if not text:
                continue
            sections.append(f"--- ARTIFACT {position}: {record.display_name} ---\n{text}")

        if not sections:
            return None

        combined = "\n\n".join(sections)
        if len(combined) > self.max_input_chars:
            combined = combined[: self.max_input_chars]
            truncated = True
        if not combined.strip():
            return None

        prefix = ""
        if truncated:
            prefix = "NOTICE: The case content was truncated to the configured input limit.\n\n"
        return f"{prefix}{combined}"
