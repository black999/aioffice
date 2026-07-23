from dataclasses import dataclass

from aioffice.application import (
    CaseRepository,
    PersistedCase,
    PersistedReplyDraft,
    ReplyDraftRepository,
    ReplyDraftStatus,
)
from aioffice.application.services import CaseDashboardService, CaseWorkspaceService
from aioffice.application.storage import ArtifactStorageReader
from aioffice.domain import Case, Identifier


@dataclass(slots=True)
class _FakeCaseRepository(CaseRepository):
    cases: tuple[PersistedCase, ...]

    def save(self, case: Case, reference_number: int, artifact_records=None) -> None:
        raise NotImplementedError

    def get(self, case_id: Identifier) -> PersistedCase | None:
        return next((case for case in self.cases if case.case.id == case_id), None)

    def get_by_artifact_locator(self, locator: str):
        raise NotImplementedError

    def list(self) -> tuple[PersistedCase, ...]:
        return self.cases

    def count(self) -> int:
        return len(self.cases)

    def get_artifact(self, case_id: Identifier, position: int):
        raise NotImplementedError


@dataclass(slots=True)
class _FakeReplyDraftRepository(ReplyDraftRepository):
    drafts: dict[Identifier, PersistedReplyDraft]
    get_statuses_calls: int = 0

    def save(self, draft: PersistedReplyDraft) -> None:
        self.drafts[draft.case_id] = draft

    def get(self, case_id: Identifier) -> PersistedReplyDraft | None:
        return self.drafts.get(case_id)

    def get_statuses(self, case_ids: tuple[Identifier, ...]) -> dict[Identifier, ReplyDraftStatus]:
        self.get_statuses_calls += 1
        return {
            case_id: draft.status
            for case_id, draft in self.drafts.items()
            if case_id in case_ids
        }

    def delete(self, case_id: Identifier) -> None:
        self.drafts.pop(case_id, None)


@dataclass(slots=True)
class _FakeStorageReader(ArtifactStorageReader):
    def open_artifact(self, storage_reference):
        raise NotImplementedError

    def get_artifact_size(self, storage_reference) -> int:
        raise NotImplementedError


def test_case_dashboard_service_includes_reply_draft_statuses_without_n_plus_one() -> None:
    first_case = PersistedCase(
        case=Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        reference_number=1,
        status="open",
        created_at="2026-07-23T10:00:00+00:00",
    )
    second_case = PersistedCase(
        case=Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
        reference_number=2,
        status="open",
        created_at="2026-07-23T10:01:00+00:00",
    )
    drafts = _FakeReplyDraftRepository(
        drafts={
            first_case.case.id: PersistedReplyDraft(
                case_id=first_case.case.id,
                subject="Temat",
                body="Tresc",
                status=ReplyDraftStatus.GENERATED,
                model_name="qwen3:4b",
                operator_instruction=None,
                approved_by=None,
                approved_at=None,
                created_at="2026-07-23T10:00:00+00:00",
                updated_at="2026-07-23T10:00:00+00:00",
            )
        }
    )

    summaries = CaseDashboardService(
        repository=_FakeCaseRepository(cases=(first_case, second_case)),
        reply_draft_repository=drafts,
    ).list_cases()

    assert drafts.get_statuses_calls == 1
    assert summaries[0].reply_draft_status_label == "Wygenerowany"
    assert summaries[1].reply_draft_status_label is None


def test_case_workspace_service_includes_reply_draft_summary() -> None:
    persisted_case = PersistedCase(
        case=Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        reference_number=1,
        status="open",
        created_at="2026-07-23T10:00:00+00:00",
        artifact_records=(),
    )
    draft = PersistedReplyDraft(
        case_id=persisted_case.case.id,
        subject="Temat",
        body="Tresc",
        status=ReplyDraftStatus.EDITED,
        model_name="qwen3:4b",
        operator_instruction="Uprzejmie",
        approved_by=None,
        approved_at=None,
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T11:00:00+00:00",
    )

    workspace = CaseWorkspaceService(
        repository=_FakeCaseRepository(cases=(persisted_case,)),
        storage_reader=_FakeStorageReader(),
        reply_draft_repository=_FakeReplyDraftRepository(drafts={persisted_case.case.id: draft}),
    ).get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.reply_draft is not None
    assert workspace.reply_draft.subject == "Temat"
    assert workspace.reply_draft.status_label == "Edytowany"
    assert workspace.reply_draft.operator_instruction == "Uprzejmie"
    assert workspace.reply_draft.approved_by is None
    assert workspace.reply_draft.approved_at is None
    assert workspace.reply_draft.is_approved is False


def test_case_dashboard_service_formats_approved_reply_draft_status() -> None:
    persisted_case = PersistedCase(
        case=Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        reference_number=1,
        status="open",
        created_at="2026-07-23T10:00:00+00:00",
    )
    drafts = _FakeReplyDraftRepository(
        drafts={
            persisted_case.case.id: PersistedReplyDraft(
                case_id=persisted_case.case.id,
                subject="Temat",
                body="Tresc",
                status=ReplyDraftStatus.APPROVED,
                model_name="qwen3:4b",
                operator_instruction=None,
                approved_by="Jan Kowalski",
                approved_at="2026-07-23T10:05:00+00:00",
                created_at="2026-07-23T10:00:00+00:00",
                updated_at="2026-07-23T10:05:00+00:00",
            )
        }
    )

    summaries = CaseDashboardService(
        repository=_FakeCaseRepository(cases=(persisted_case,)),
        reply_draft_repository=drafts,
    ).list_cases()

    assert summaries[0].reply_draft_status_label == "Zatwierdzony"


def test_case_workspace_service_includes_approved_reply_draft_metadata() -> None:
    persisted_case = PersistedCase(
        case=Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        reference_number=1,
        status="open",
        created_at="2026-07-23T10:00:00+00:00",
        artifact_records=(),
    )
    draft = PersistedReplyDraft(
        case_id=persisted_case.case.id,
        subject="Temat",
        body="Tresc",
        status=ReplyDraftStatus.APPROVED,
        model_name="qwen3:4b",
        operator_instruction="Uprzejmie",
        approved_by="Jan Kowalski",
        approved_at="2026-07-23T10:05:00+00:00",
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:05:00+00:00",
    )

    workspace = CaseWorkspaceService(
        repository=_FakeCaseRepository(cases=(persisted_case,)),
        storage_reader=_FakeStorageReader(),
        reply_draft_repository=_FakeReplyDraftRepository(drafts={persisted_case.case.id: draft}),
    ).get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.reply_draft is not None
    assert workspace.reply_draft.status_label == "Zatwierdzony"
    assert workspace.reply_draft.approved_by == "Jan Kowalski"
    assert workspace.reply_draft.approved_at == "2026-07-23T10:05:00+00:00"
    assert workspace.reply_draft.is_approved is True
