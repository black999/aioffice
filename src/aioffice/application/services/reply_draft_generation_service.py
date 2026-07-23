"""Application service for manual AI reply draft generation."""

from __future__ import annotations

from dataclasses import dataclass
from io import TextIOWrapper

from aioffice.application import (
    ArtifactRecord,
    ArtifactStorageReader,
    CaseClassificationRepository,
    CaseRepository,
    ReplyDraftGenerationResult,
    ReplyDraftGenerator,
    ReplyDraftRepository,
    ReplyDraftStatus,
    build_persisted_reply_draft,
    normalize_operator_instruction,
)
from aioffice.application.storage import ArtifactNotFoundError, UnsupportedStorageError
from aioffice.domain import ArtifactType, Identifier


@dataclass(slots=True)
class ReplyDraftGenerationService:
    """Generate a reply draft from persisted TEXT artifacts."""

    case_repository: CaseRepository
    classification_repository: CaseClassificationRepository
    reply_draft_repository: ReplyDraftRepository
    storage_reader: ArtifactStorageReader
    generator: ReplyDraftGenerator
    max_input_chars: int
    max_operator_instruction_chars: int

    def generate_reply_draft(
        self,
        case_id: Identifier,
        *,
        operator_instruction: str | None = None,
        force: bool = False,
    ) -> ReplyDraftGenerationResult | None:
        """Run manual reply draft generation for one case."""

        persisted_case = self.case_repository.get(case_id)
        if persisted_case is None:
            return None

        existing_draft = self.reply_draft_repository.get(case_id)
        if existing_draft is not None and not force:
            return ReplyDraftGenerationResult(
                draft=existing_draft,
                skipped=True,
                reason="already_generated",
            )

        normalized_instruction = normalize_operator_instruction(
            operator_instruction,
            max_chars=self.max_operator_instruction_chars,
        )
        case_text = self._build_input_text(persisted_case.artifact_records)
        if case_text is None:
            return ReplyDraftGenerationResult(
                draft=existing_draft,
                skipped=True,
                reason="no_text",
            )

        persisted_classification = self.classification_repository.get(case_id)
        generated_draft = self.generator.generate(
            case_text=case_text,
            category=(
                persisted_classification.category
                if persisted_classification is not None
                else None
            ),
            operator_instruction=normalized_instruction,
        )
        persisted_draft = build_persisted_reply_draft(
            case_id=case_id,
            generated_draft=generated_draft,
            operator_instruction=normalized_instruction,
            existing_draft=existing_draft,
            status=ReplyDraftStatus.GENERATED,
        )
        self.reply_draft_repository.save(persisted_draft)
        return ReplyDraftGenerationResult(
            draft=persisted_draft,
            skipped=False,
            reason=None,
        )

    def _build_input_text(self, artifact_records: tuple[ArtifactRecord, ...]) -> str | None:
        sections: list[str] = []
        remaining_chars = self.max_input_chars
        truncated = False
        for position, record in enumerate(artifact_records):
            if record.artifact.artifact_type is not ArtifactType.TEXT:
                continue

            separator = "\n\n" if sections else ""
            header = f"--- ARTIFACT {position}: {record.display_name} ---\n"
            reserved_chars = len(separator) + len(header)
            if remaining_chars <= reserved_chars:
                truncated = True
                break

            try:
                text, record_truncated = self._read_text_record(record, remaining_chars - reserved_chars)
            except (ArtifactNotFoundError, UnsupportedStorageError, OSError, UnicodeError):
                continue

            if text is None:
                continue

            sections.append(f"{separator}{header}{text}")
            remaining_chars -= len(separator) + len(header) + len(text)
            if record_truncated or remaining_chars <= 0:
                truncated = True
                break

        if not sections:
            return None

        combined = "".join(sections)
        if not combined.strip():
            return None
        if truncated:
            return (
                "NOTICE: The case content was truncated to the configured input limit.\n\n"
                f"{combined}"
            )
        return combined

    def _read_text_record(self, record: ArtifactRecord, char_limit: int) -> tuple[str | None, bool]:
        if char_limit <= 0:
            return None, False

        with self.storage_reader.open_artifact(record.artifact.storage_reference) as handle:
            reader = TextIOWrapper(handle, encoding="utf-8", errors="replace")
            try:
                chunks: list[str] = []
                remaining = char_limit
                truncated = False
                while remaining > 0:
                    chunk = reader.read(min(4096, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if remaining <= 0 and reader.read(1):
                    truncated = True
                normalized = "".join(chunks).strip() or None
                return normalized, truncated
            finally:
                reader.detach()
