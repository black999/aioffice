"""Application service for manual reply draft editing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from aioffice.application import (
    GeneratedReplyDraft,
    PersistedReplyDraft,
    ReplyDraftRepository,
    ReplyDraftStatus,
    build_persisted_reply_draft,
    validate_manual_reply_draft_body,
    validate_manual_reply_draft_subject,
)
from aioffice.domain import Identifier


@dataclass(slots=True)
class ReplyDraftEditingService:
    """Edit the currently persisted reply draft for a case."""

    repository: ReplyDraftRepository

    def update_reply_draft(
        self,
        case_id: Identifier,
        *,
        subject: str,
        body: str,
    ) -> PersistedReplyDraft | None:
        """Validate and persist a manually edited reply draft."""

        existing_draft = self.repository.get(case_id)
        if existing_draft is None:
            return None

        normalized_subject = validate_manual_reply_draft_subject(subject)
        normalized_body = validate_manual_reply_draft_body(body)
        updated_draft = build_persisted_reply_draft(
            case_id=case_id,
            generated_draft=GeneratedReplyDraft(
                subject=normalized_subject,
                body=normalized_body,
                model_name=existing_draft.model_name,
            ),
            operator_instruction=existing_draft.operator_instruction,
            existing_draft=existing_draft,
            status=ReplyDraftStatus.EDITED,
            created_at=existing_draft.created_at,
            updated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self.repository.save(updated_draft)
        return updated_draft
