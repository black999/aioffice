from dataclasses import dataclass

import pytest

from aioffice.application import PersistedReplyDraft, ReplyDraftRepository, ReplyDraftStatus
from aioffice.application.services import ReplyDraftApprovalService
from aioffice.domain import Identifier


@dataclass(slots=True)
class _FakeReplyDraftRepository(ReplyDraftRepository):
    draft: PersistedReplyDraft | None
    saved_draft: PersistedReplyDraft | None = None

    def save(self, draft: PersistedReplyDraft) -> None:
        self.saved_draft = draft
        self.draft = draft

    def get(self, case_id: Identifier) -> PersistedReplyDraft | None:
        if self.draft is None or self.draft.case_id != case_id:
            return None
        return self.draft

    def get_statuses(self, case_ids: tuple[Identifier, ...]) -> dict[Identifier, ReplyDraftStatus]:
        return {}

    def delete(self, case_id: Identifier) -> None:
        if self.draft is not None and self.draft.case_id == case_id:
            self.draft = None


def _draft(
    *,
    status: ReplyDraftStatus = ReplyDraftStatus.GENERATED,
    approved_by: str | None = None,
    approved_at: str | None = None,
) -> PersistedReplyDraft:
    return PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Temat",
        body="Tresc",
        status=status,
        model_name="qwen3:4b",
        operator_instruction="Uprzejmie",
        approved_by=approved_by,
        approved_at=approved_at,
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:00:00+00:00",
    )


def test_reply_draft_approval_service_approves_generated_draft() -> None:
    repository = _FakeReplyDraftRepository(draft=_draft())
    service = ReplyDraftApprovalService(repository=repository)

    approved = service.approve_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        approved_by="Jan Kowalski",
    )

    assert approved is not None
    assert approved.status is ReplyDraftStatus.APPROVED
    assert approved.approved_by == "Jan Kowalski"
    assert approved.approved_at is not None
    assert approved.updated_at == approved.approved_at
    assert approved.created_at == "2026-07-23T10:00:00+00:00"
    assert approved.subject == "Temat"
    assert approved.body == "Tresc"
    assert approved.model_name == "qwen3:4b"
    assert approved.operator_instruction == "Uprzejmie"


def test_reply_draft_approval_service_approves_edited_draft() -> None:
    repository = _FakeReplyDraftRepository(
        draft=_draft(status=ReplyDraftStatus.EDITED),
    )
    service = ReplyDraftApprovalService(repository=repository)

    approved = service.approve_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        approved_by="Operator 1",
    )

    assert approved is not None
    assert approved.status is ReplyDraftStatus.APPROVED
    assert approved.approved_by == "Operator 1"


def test_reply_draft_approval_service_reapproves_existing_approved_draft() -> None:
    repository = _FakeReplyDraftRepository(
        draft=_draft(
            status=ReplyDraftStatus.APPROVED,
            approved_by="Jan Kowalski",
            approved_at="2026-07-23T10:05:00+00:00",
        ),
    )
    service = ReplyDraftApprovalService(repository=repository)

    approved = service.approve_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        approved_by="Anna Nowak",
    )

    assert approved is not None
    assert approved.status is ReplyDraftStatus.APPROVED
    assert approved.approved_by == "Anna Nowak"
    assert approved.approved_at is not None
    assert approved.approved_at >= "2026-07-23T10:05:00+00:00"


def test_reply_draft_approval_service_returns_none_for_missing_draft() -> None:
    service = ReplyDraftApprovalService(repository=_FakeReplyDraftRepository(draft=None))

    approved = service.approve_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        approved_by="Jan Kowalski",
    )

    assert approved is None


def test_reply_draft_approval_service_rejects_blank_approver_name() -> None:
    service = ReplyDraftApprovalService(repository=_FakeReplyDraftRepository(draft=_draft()))

    with pytest.raises(ValueError, match="approved_by must be a non-empty string"):
        service.approve_reply_draft(
            Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            approved_by="   ",
        )


def test_reply_draft_approval_service_revokes_approval_and_keeps_content() -> None:
    repository = _FakeReplyDraftRepository(
        draft=_draft(
            status=ReplyDraftStatus.APPROVED,
            approved_by="Jan Kowalski",
            approved_at="2026-07-23T10:05:00+00:00",
        ),
    )
    service = ReplyDraftApprovalService(repository=repository)

    revoked = service.revoke_reply_draft_approval(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    assert revoked is not None
    assert revoked.status is ReplyDraftStatus.EDITED
    assert revoked.approved_by is None
    assert revoked.approved_at is None
    assert revoked.updated_at >= "2026-07-23T10:05:00+00:00"
    assert revoked.created_at == "2026-07-23T10:00:00+00:00"
    assert revoked.subject == "Temat"
    assert revoked.body == "Tresc"


@pytest.mark.parametrize("status", [ReplyDraftStatus.GENERATED, ReplyDraftStatus.EDITED])
def test_reply_draft_approval_service_revoke_is_neutral_for_non_approved_status(
    status: ReplyDraftStatus,
) -> None:
    existing = _draft(status=status)
    service = ReplyDraftApprovalService(repository=_FakeReplyDraftRepository(draft=existing))

    revoked = service.revoke_reply_draft_approval(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    assert revoked == existing


def test_reply_draft_approval_service_revoke_returns_none_for_missing_draft() -> None:
    service = ReplyDraftApprovalService(repository=_FakeReplyDraftRepository(draft=None))

    revoked = service.revoke_reply_draft_approval(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    assert revoked is None
