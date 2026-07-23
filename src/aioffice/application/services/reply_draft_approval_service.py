"""Application services for manual reply draft approval workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from aioffice.application import (
    GeneratedReplyDraft,
    PersistedReplyDraft,
    ReplyDraftRepository,
    ReplyDraftStatus,
    build_persisted_reply_draft,
    normalize_approver_name,
)
from aioffice.domain import Identifier


@dataclass(slots=True)
class ReplyDraftApprovalService:
    """Approve or revoke the latest reply draft for a case."""

    repository: ReplyDraftRepository

    def approve_reply_draft(
        self,
        case_id: Identifier,
        *,
        approved_by: str,
    ) -> PersistedReplyDraft | None:
        """Approve the current draft version for a case."""

        existing_draft = self.repository.get(case_id)
        if existing_draft is None:
            return None

        timestamp = datetime.now(UTC).isoformat(timespec="seconds")
        approved_draft = build_persisted_reply_draft(
            case_id=case_id,
            generated_draft=GeneratedReplyDraft(
                subject=existing_draft.subject,
                body=existing_draft.body,
                model_name=existing_draft.model_name,
            ),
            operator_instruction=existing_draft.operator_instruction,
            existing_draft=existing_draft,
            status=ReplyDraftStatus.APPROVED,
            approved_by=normalize_approver_name(approved_by),
            approved_at=timestamp,
            created_at=existing_draft.created_at,
            updated_at=timestamp,
        )
        self.repository.save(approved_draft)
        return approved_draft

    def revoke_reply_draft_approval(
        self,
        case_id: Identifier,
    ) -> PersistedReplyDraft | None:
        """Clear approval metadata from the current draft if necessary."""

        existing_draft = self.repository.get(case_id)
        if existing_draft is None:
            return None
        if existing_draft.status is not ReplyDraftStatus.APPROVED:
            return existing_draft

        revoked_draft = build_persisted_reply_draft(
            case_id=case_id,
            generated_draft=GeneratedReplyDraft(
                subject=existing_draft.subject,
                body=existing_draft.body,
                model_name=existing_draft.model_name,
            ),
            operator_instruction=existing_draft.operator_instruction,
            existing_draft=existing_draft,
            status=ReplyDraftStatus.EDITED,
            created_at=existing_draft.created_at,
            updated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self.repository.save(revoked_draft)
        return revoked_draft
