"""Application service for extracting text from persisted documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from aioffice.application import (
    ArtifactRecord,
    ArtifactStorageReader,
    CaseRepository,
    DocumentExtractionResult,
    DocumentStorage,
    DocumentTextExtractor,
    DownloadableArtifact,
    sanitize_display_name,
)
from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DocumentExtractionService:
    """Extract TEXT artifacts from supported stored documents."""

    repository: CaseRepository
    storage: DocumentStorage
    storage_reader: ArtifactStorageReader
    extractors: tuple[DocumentTextExtractor, ...]
    max_input_bytes: int
    max_output_chars: int

    def extract_case_documents(self, case_id: Identifier) -> DocumentExtractionResult | None:
        """Extract text artifacts for supported documents within one case."""

        persisted_case = self.repository.get(case_id)
        if persisted_case is None:
            return None

        case = self._copy_case(persisted_case.case)
        records_to_save = list(persisted_case.artifact_records)
        used_display_names = {record.display_name for record in records_to_save}
        extracted = 0
        skipped = 0
        failed = 0

        for position, record in enumerate(persisted_case.artifact_records):
            if record.artifact.artifact_type not in {ArtifactType.ATTACHMENT, ArtifactType.PDF}:
                continue
            if self._has_extracted_text(records_to_save, source_position=position):
                skipped += 1
                continue

            downloadable_artifact = self.repository.get_artifact(case_id, position)
            if downloadable_artifact is None:
                failed += 1
                logger.exception(
                    "Document text extraction failed: case_id=%s position=%s",
                    case_id,
                    position,
                )
                continue

            extractor = self._select_extractor(downloadable_artifact)
            if extractor is None:
                skipped += 1
                continue

            try:
                artifact_size = self.storage_reader.get_artifact_size(downloadable_artifact.storage_reference)
                if artifact_size > self.max_input_bytes:
                    failed += 1
                    logger.warning(
                        "Document text extraction skipped oversized file: case_id=%s position=%s",
                        case_id,
                        position,
                    )
                    continue

                with self.storage_reader.open_artifact(downloadable_artifact.storage_reference) as source:
                    extracted_text = extractor.extract_text(source)
            except Exception:
                failed += 1
                logger.exception(
                    "Document text extraction failed: case_id=%s position=%s",
                    case_id,
                    position,
                )
                continue

            if extracted_text is None:
                skipped += 1
                logger.info(
                    "Document text extraction found no usable text: case_id=%s position=%s",
                    case_id,
                    position,
                )
                continue

            normalized_text = extracted_text.replace("\r\n", "\n").replace("\r", "\n")
            output_text = normalized_text
            is_truncated = False
            if len(output_text) > self.max_output_chars:
                output_text = output_text[: self.max_output_chars]
                is_truncated = True

            display_name = self._build_output_display_name(
                source_display_name=downloadable_artifact.display_name,
                source_position=position,
                used_display_names=used_display_names,
            )
            storage_reference = self._store_text(output_text)
            text_artifact = Artifact(
                artifact_type=ArtifactType.TEXT,
                storage_reference=storage_reference,
            )
            case.add_artifact(text_artifact)
            records_to_save.append(
                ArtifactRecord(
                    artifact=text_artifact,
                    display_name=display_name,
                    content_type="text/plain; charset=utf-8",
                    source_position=position,
                    is_truncated=is_truncated,
                )
            )
            extracted += 1

        if extracted == 0 and failed == 0:
            return DocumentExtractionResult(extracted=0, skipped=skipped, failed=0)
        if extracted == 0 and failed > 0:
            return DocumentExtractionResult(extracted=0, skipped=skipped, failed=failed)

        self.repository.save(
            case,
            persisted_case.reference_number,
            artifact_records=tuple(records_to_save),
        )
        return DocumentExtractionResult(extracted=extracted, skipped=skipped, failed=failed)

    def _copy_case(self, source_case: Case) -> Case:
        case = Case(id=source_case.id)
        for artifact in source_case.artifacts:
            case.add_artifact(artifact)
        case.pull_events()
        return case

    def _has_extracted_text(
        self,
        artifact_records: list[ArtifactRecord],
        *,
        source_position: int,
    ) -> bool:
        return any(
            record.artifact.artifact_type is ArtifactType.TEXT
            and record.source_position == source_position
            for record in artifact_records
        )

    def _select_extractor(self, artifact: DownloadableArtifact) -> DocumentTextExtractor | None:
        for extractor in self.extractors:
            if extractor.supports(artifact):
                return extractor
        return None

    def _build_output_display_name(
        self,
        *,
        source_display_name: str,
        source_position: int,
        used_display_names: set[str],
    ) -> str:
        source_path = Path(source_display_name)
        if source_path.suffix:
            fallback = f"document-{source_position:03d}.txt"
            candidate = sanitize_display_name(
                f"{source_path.stem}.txt",
                fallback=fallback,
            )
        else:
            candidate = sanitize_display_name(
                source_display_name,
                fallback=f"document-{source_position:03d}.txt",
            )
            candidate = f"{Path(candidate).stem}.txt"
        final_candidate = candidate
        suffix_index = 2
        while final_candidate in used_display_names:
            stem = Path(candidate).stem
            final_candidate = f"{stem}-{suffix_index}.txt"
            suffix_index += 1
        used_display_names.add(final_candidate)
        return final_candidate

    def _store_text(self, body_text: str) -> StorageReference:
        with NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8", newline="\n") as file:
            temporary_path = Path(file.name)
            file.write(body_text)
        try:
            return self.storage.store_file(temporary_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
