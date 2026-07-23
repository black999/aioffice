from dataclasses import dataclass

import pytest

from aioffice.application import PersistedReplyDraft, ReplyDraftRepository, ReplyDraftStatus
from aioffice.application.services import ReplyDraftEditingService
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


def _draft() -> PersistedReplyDraft:
    return PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Stary temat",
        body="Stara tresc",
        status=ReplyDraftStatus.GENERATED,
        model_name="qwen3:4b",
        operator_instruction="Uprzejmie",
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:00:00+00:00",
    )


def test_reply_draft_editing_service_updates_draft_and_sets_edited_status() -> None:
    repository = _FakeReplyDraftRepository(draft=_draft())
    service = ReplyDraftEditingService(repository=repository)

    updated = service.update_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Nowy temat",
        body="Nowa tresc",
    )

    assert updated is not None
    assert updated.subject == "Nowy temat"
    assert updated.body == "Nowa tresc"
    assert updated.status is ReplyDraftStatus.EDITED
    assert updated.created_at == "2026-07-23T10:00:00+00:00"
    assert updated.updated_at >= "2026-07-23T10:00:00+00:00"
    assert updated.model_name == "qwen3:4b"


def test_reply_draft_editing_service_returns_none_when_draft_missing() -> None:
    service = ReplyDraftEditingService(repository=_FakeReplyDraftRepository(draft=None))

    result = service.update_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Nowy temat",
        body="Nowa tresc",
    )

    assert result is None


def test_reply_draft_editing_service_rejects_invalid_manual_values() -> None:
    service = ReplyDraftEditingService(repository=_FakeReplyDraftRepository(draft=_draft()))

    with pytest.raises(ValueError, match="subject must be a non-empty string"):
        service.update_reply_draft(
            Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            subject="   ",
            body="Nowa tresc",
        )
