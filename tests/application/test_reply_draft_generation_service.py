from dataclasses import dataclass
from io import BytesIO

import pytest

from aioffice.application import (
    ArtifactRecord,
    CaseCategory,
    CaseClassificationRepository,
    CaseRepository,
    GeneratedReplyDraft,
    PersistedCase,
    PersistedCaseClassification,
    PersistedReplyDraft,
    ReplyDraftGenerationError,
    ReplyDraftGenerator,
    ReplyDraftRepository,
    ReplyDraftStatus,
)
from aioffice.application.services import ReplyDraftGenerationService
from aioffice.application.storage import ArtifactNotFoundError, ArtifactStorageReader
from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference


@dataclass(slots=True)
class _FakeCaseRepository(CaseRepository):
    persisted_case: PersistedCase | None

    def save(self, case: Case, reference_number: int, artifact_records=None) -> None:
        raise NotImplementedError

    def get(self, case_id: Identifier) -> PersistedCase | None:
        if self.persisted_case is None or self.persisted_case.case.id != case_id:
            return None
        return self.persisted_case

    def get_by_artifact_locator(self, locator: str):
        raise NotImplementedError

    def list(self):
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def get_artifact(self, case_id: Identifier, position: int):
        raise NotImplementedError


@dataclass(slots=True)
class _FakeClassificationRepository(CaseClassificationRepository):
    classification: PersistedCaseClassification | None = None

    def save(self, classification: PersistedCaseClassification) -> None:
        self.classification = classification

    def get(self, case_id: Identifier) -> PersistedCaseClassification | None:
        return self.classification

    def get_many(self, case_ids: tuple[Identifier, ...]):
        return {}

    def delete(self, case_id: Identifier) -> None:
        self.classification = None


@dataclass(slots=True)
class _FakeReplyDraftRepository(ReplyDraftRepository):
    draft: PersistedReplyDraft | None = None
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
        self.draft = None


@dataclass(slots=True)
class _FakeStorageReader(ArtifactStorageReader):
    content_by_locator: dict[str, bytes]
    failing_locators: set[str]

    def open_artifact(self, storage_reference: StorageReference):
        if storage_reference.locator in self.failing_locators:
            raise ArtifactNotFoundError("missing")
        return BytesIO(self.content_by_locator[storage_reference.locator])

    def get_artifact_size(self, storage_reference: StorageReference) -> int:
        return len(self.content_by_locator[storage_reference.locator])


@dataclass(slots=True)
class _FakeGenerator(ReplyDraftGenerator):
    result: GeneratedReplyDraft
    exception: Exception | None = None
    seen_case_text: str | None = None
    seen_category: CaseCategory | None = None
    seen_operator_instruction: str | None = None
    calls: int = 0

    def generate(self, *, case_text: str, category: CaseCategory | None, operator_instruction: str | None):
        self.calls += 1
        self.seen_case_text = case_text
        self.seen_category = category
        self.seen_operator_instruction = operator_instruction
        if self.exception is not None:
            raise self.exception
        return self.result


def _artifact_record(position: int, display_name: str, locator: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact=Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(storage_name="filesystem", locator=locator),
        ),
        display_name=display_name,
        content_type="text/plain",
        source_position=position,
    )


def _persisted_case(*records: ArtifactRecord) -> PersistedCase:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    for record in records:
        case.add_artifact(record.artifact)
    return PersistedCase(
        case=case,
        reference_number=1,
        status="open",
        created_at="2026-07-23T10:00:00+00:00",
        artifact_records=records,
    )


def test_reply_draft_generation_service_generates_from_text_artifacts_in_order() -> None:
    records = (
        _artifact_record(0, "message.txt", "artifacts/aa/message.txt"),
        _artifact_record(1, "invoice.txt", "artifacts/aa/invoice.txt"),
    )
    generator = _FakeGenerator(
        result=GeneratedReplyDraft(subject="Temat", body="Tresc", model_name="qwen3:4b")
    )
    service = ReplyDraftGenerationService(
        case_repository=_FakeCaseRepository(persisted_case=_persisted_case(*records)),
        classification_repository=_FakeClassificationRepository(
            classification=PersistedCaseClassification(
                case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                category=CaseCategory.INVOICE,
                confidence=0.9,
                rationale="Dotyczy faktury",
                model_name="qwen2.5:7b",
                classified_at="2026-07-23T09:59:00+00:00",
            )
        ),
        reply_draft_repository=_FakeReplyDraftRepository(),
        storage_reader=_FakeStorageReader(
            content_by_locator={
                "artifacts/aa/message.txt": b"Pierwszy tekst",
                "artifacts/aa/invoice.txt": b"Drugi tekst",
            },
            failing_locators=set(),
        ),
        generator=generator,
        max_input_chars=10_000,
        max_operator_instruction_chars=2000,
    )

    result = service.generate_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        operator_instruction="  Uprzejmie odpowiedz  ",
    )

    assert result is not None
    assert result.skipped is False
    assert result.draft is not None
    assert result.draft.status is ReplyDraftStatus.GENERATED
    assert generator.seen_category is CaseCategory.INVOICE
    assert generator.seen_operator_instruction == "Uprzejmie odpowiedz"
    assert generator.seen_case_text is not None
    assert "--- ARTIFACT 0: message.txt ---" in generator.seen_case_text
    assert "--- ARTIFACT 1: invoice.txt ---" in generator.seen_case_text
    assert generator.seen_case_text.index("message.txt") < generator.seen_case_text.index("invoice.txt")


def test_reply_draft_generation_service_returns_no_text_when_no_text_artifacts_are_usable() -> None:
    record = _artifact_record(0, "message.txt", "artifacts/aa/message.txt")
    service = ReplyDraftGenerationService(
        case_repository=_FakeCaseRepository(persisted_case=_persisted_case(record)),
        classification_repository=_FakeClassificationRepository(),
        reply_draft_repository=_FakeReplyDraftRepository(),
        storage_reader=_FakeStorageReader(content_by_locator={}, failing_locators={"artifacts/aa/message.txt"}),
        generator=_FakeGenerator(
            result=GeneratedReplyDraft(subject="Temat", body="Tresc", model_name="qwen3:4b")
        ),
        max_input_chars=10_000,
        max_operator_instruction_chars=2000,
    )

    result = service.generate_reply_draft(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert result is not None
    assert result.skipped is True
    assert result.reason == "no_text"


def test_reply_draft_generation_service_skips_existing_draft_without_force() -> None:
    existing_draft = PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Istniejacy",
        body="Istniejaca tresc",
        status=ReplyDraftStatus.GENERATED,
        model_name="qwen3:4b",
        operator_instruction=None,
        approved_by=None,
        approved_at=None,
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:00:00+00:00",
    )
    service = ReplyDraftGenerationService(
        case_repository=_FakeCaseRepository(persisted_case=_persisted_case()),
        classification_repository=_FakeClassificationRepository(),
        reply_draft_repository=_FakeReplyDraftRepository(draft=existing_draft),
        storage_reader=_FakeStorageReader(content_by_locator={}, failing_locators=set()),
        generator=_FakeGenerator(
            result=GeneratedReplyDraft(subject="Temat", body="Tresc", model_name="qwen3:4b")
        ),
        max_input_chars=10_000,
        max_operator_instruction_chars=2000,
    )

    result = service.generate_reply_draft(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert result is not None
    assert result.skipped is True
    assert result.reason == "already_generated"


def test_reply_draft_generation_service_force_replaces_existing_draft_and_keeps_created_at() -> None:
    record = _artifact_record(0, "message.txt", "artifacts/aa/message.txt")
    existing_draft = PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Stary temat",
        body="Stara tresc",
        status=ReplyDraftStatus.EDITED,
        model_name="old-model",
        operator_instruction="Stara instrukcja",
        approved_by=None,
        approved_at=None,
        created_at="2026-07-23T08:00:00+00:00",
        updated_at="2026-07-23T09:00:00+00:00",
    )
    repository = _FakeReplyDraftRepository(draft=existing_draft)
    service = ReplyDraftGenerationService(
        case_repository=_FakeCaseRepository(persisted_case=_persisted_case(record)),
        classification_repository=_FakeClassificationRepository(),
        reply_draft_repository=repository,
        storage_reader=_FakeStorageReader(
            content_by_locator={"artifacts/aa/message.txt": b"Nowy tekst"},
            failing_locators=set(),
        ),
        generator=_FakeGenerator(
            result=GeneratedReplyDraft(subject="Nowy temat", body="Nowa tresc", model_name="qwen3:4b")
        ),
        max_input_chars=10_000,
        max_operator_instruction_chars=2000,
    )

    result = service.generate_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        force=True,
    )

    assert result is not None
    assert result.draft is not None
    assert result.draft.created_at == "2026-07-23T08:00:00+00:00"
    assert result.draft.updated_at >= "2026-07-23T09:00:00+00:00"
    assert result.draft.status is ReplyDraftStatus.GENERATED
    assert result.draft.approved_by is None
    assert result.draft.approved_at is None
    assert repository.saved_draft is not None


def test_reply_draft_generation_service_force_replaces_approved_draft_and_clears_approval() -> None:
    record = _artifact_record(0, "message.txt", "artifacts/aa/message.txt")
    existing_draft = PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Stary temat",
        body="Stara tresc",
        status=ReplyDraftStatus.APPROVED,
        model_name="old-model",
        operator_instruction="Stara instrukcja",
        approved_by="Jan Kowalski",
        approved_at="2026-07-23T09:30:00+00:00",
        created_at="2026-07-23T08:00:00+00:00",
        updated_at="2026-07-23T09:30:00+00:00",
    )
    repository = _FakeReplyDraftRepository(draft=existing_draft)
    service = ReplyDraftGenerationService(
        case_repository=_FakeCaseRepository(persisted_case=_persisted_case(record)),
        classification_repository=_FakeClassificationRepository(),
        reply_draft_repository=repository,
        storage_reader=_FakeStorageReader(
            content_by_locator={"artifacts/aa/message.txt": b"Nowy tekst"},
            failing_locators=set(),
        ),
        generator=_FakeGenerator(
            result=GeneratedReplyDraft(subject="Nowy temat", body="Nowa tresc", model_name="qwen3:4b")
        ),
        max_input_chars=10_000,
        max_operator_instruction_chars=2000,
    )

    result = service.generate_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        force=True,
    )

    assert result is not None
    assert result.draft is not None
    assert result.draft.status is ReplyDraftStatus.GENERATED
    assert result.draft.approved_by is None
    assert result.draft.approved_at is None
    assert result.draft.created_at == "2026-07-23T08:00:00+00:00"
    assert result.draft.updated_at >= "2026-07-23T09:30:00+00:00"


def test_reply_draft_generation_service_returns_none_for_missing_case() -> None:
    service = ReplyDraftGenerationService(
        case_repository=_FakeCaseRepository(persisted_case=None),
        classification_repository=_FakeClassificationRepository(),
        reply_draft_repository=_FakeReplyDraftRepository(),
        storage_reader=_FakeStorageReader(content_by_locator={}, failing_locators=set()),
        generator=_FakeGenerator(
            result=GeneratedReplyDraft(subject="Temat", body="Tresc", model_name="qwen3:4b")
        ),
        max_input_chars=10_000,
        max_operator_instruction_chars=2000,
    )

    assert service.generate_reply_draft(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    ) is None


def test_reply_draft_generation_service_does_not_save_on_generator_error() -> None:
    record = _artifact_record(0, "message.txt", "artifacts/aa/message.txt")
    repository = _FakeReplyDraftRepository()
    service = ReplyDraftGenerationService(
        case_repository=_FakeCaseRepository(persisted_case=_persisted_case(record)),
        classification_repository=_FakeClassificationRepository(),
        reply_draft_repository=repository,
        storage_reader=_FakeStorageReader(
            content_by_locator={"artifacts/aa/message.txt": b"Tekst"},
            failing_locators=set(),
        ),
        generator=_FakeGenerator(
            result=GeneratedReplyDraft(subject="Temat", body="Tresc", model_name="qwen3:4b"),
            exception=ReplyDraftGenerationError("boom"),
        ),
        max_input_chars=10_000,
        max_operator_instruction_chars=2000,
    )

    with pytest.raises(ReplyDraftGenerationError):
        service.generate_reply_draft(
            Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        )

    assert repository.saved_draft is None
