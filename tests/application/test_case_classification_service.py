from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

import pytest

from aioffice.application import (
    ArtifactRecord,
    ArtifactStorageReader,
    CaseCategory,
    CaseClassification,
    CaseClassificationError,
    CaseClassificationRepository,
    CaseClassifier,
    CaseRepository,
    PersistedCase,
    PersistedCaseClassification,
)
from aioffice.application.services import CaseClassificationService
from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference


@dataclass(slots=True)
class _FakeCaseRepository(CaseRepository):
    persisted_case: PersistedCase | None

    def save(
        self,
        case: Case,
        reference_number: int,
        artifact_records: tuple[ArtifactRecord, ...] | None = None,
    ) -> None:
        msg = "save is not used in this test"
        raise NotImplementedError(msg)

    def get(self, case_id: Identifier) -> PersistedCase | None:
        if self.persisted_case is None or self.persisted_case.case.id != case_id:
            return None
        return self.persisted_case

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        return None

    def list(self) -> tuple[PersistedCase, ...]:
        return () if self.persisted_case is None else (self.persisted_case,)

    def count(self) -> int:
        return 0 if self.persisted_case is None else 1

    def get_artifact(self, case_id: Identifier, position: int):
        return None


@dataclass(slots=True)
class _FakeClassificationRepository(CaseClassificationRepository):
    current: PersistedCaseClassification | None = None
    saved: PersistedCaseClassification | None = None
    save_calls: int = 0

    def save(self, classification: PersistedCaseClassification) -> None:
        self.saved = classification
        self.current = classification
        self.save_calls += 1

    def get(self, case_id: Identifier) -> PersistedCaseClassification | None:
        if self.current is None or self.current.case_id != case_id:
            return None
        return self.current

    def get_many(self, case_ids: tuple[Identifier, ...]) -> dict[Identifier, PersistedCaseClassification]:
        if self.current is None or self.current.case_id not in case_ids:
            return {}
        return {self.current.case_id: self.current}

    def delete(self, case_id: Identifier) -> None:
        if self.current is not None and self.current.case_id == case_id:
            self.current = None


@dataclass(slots=True)
class _FakeStorageReader(ArtifactStorageReader):
    contents: dict[str, bytes]
    failing_locators: set[str] = field(default_factory=set)

    def open_artifact(self, storage_reference: StorageReference):
        if storage_reference.locator in self.failing_locators:
            raise OSError("boom")
        return BytesIO(self.contents[storage_reference.locator])

    def get_artifact_size(self, storage_reference: StorageReference) -> int:
        return len(self.contents[storage_reference.locator])


@dataclass(slots=True)
class _FakeClassifier(CaseClassifier):
    result: CaseClassification
    calls: int = 0
    seen_text: str | None = None
    exception: Exception | None = None

    def classify(self, text: str) -> CaseClassification:
        self.calls += 1
        self.seen_text = text
        if self.exception is not None:
            raise self.exception
        return self.result


def _text_record(locator: str, display_name: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact=Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(storage_name="filesystem", locator=locator),
        ),
        display_name=display_name,
        content_type="text/plain; charset=utf-8",
    )


def _persisted_case(*records: ArtifactRecord) -> PersistedCase:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    for record in records:
        case.add_artifact(record.artifact)
    case.pull_events()
    return PersistedCase(
        case=case,
        reference_number=1,
        status="open",
        created_at="2026-07-23T12:00:00+00:00",
        artifact_records=records,
    )


def _service(
    persisted_case: PersistedCase | None,
    *,
    current_classification: PersistedCaseClassification | None = None,
    contents: dict[str, bytes] | None = None,
    classifier: _FakeClassifier | None = None,
    max_input_chars: int = 100_000,
) -> tuple[CaseClassificationService, _FakeClassificationRepository, _FakeClassifier]:
    fake_classifier = classifier or _FakeClassifier(
        result=CaseClassification(
            category=CaseCategory.INVOICE,
            confidence=0.92,
            rationale="Invoice-related content",
            model_name="qwen2.5:7b",
        )
    )
    classification_repository = _FakeClassificationRepository(current=current_classification)
    service = CaseClassificationService(
        case_repository=_FakeCaseRepository(persisted_case=persisted_case),
        classification_repository=classification_repository,
        storage_reader=_FakeStorageReader(contents=contents or {}),
        classifier=fake_classifier,
        max_input_chars=max_input_chars,
    )
    return service, classification_repository, fake_classifier


def test_classify_case_with_single_text_artifact() -> None:
    record = _text_record("artifacts/aa/bb/message.txt", "message.txt")
    service, repository, classifier = _service(
        _persisted_case(record),
        contents={"artifacts/aa/bb/message.txt": b"Hello world"},
    )

    result = service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert result is not None
    assert result.skipped is False
    assert result.classification is not None
    assert repository.saved is not None
    assert repository.saved.model_name == "qwen2.5:7b"
    assert classifier.calls == 1


def test_classify_case_uses_multiple_text_artifacts_in_order_and_without_locator() -> None:
    first = _text_record("artifacts/aa/bb/message.txt", "message.txt")
    second = _text_record("artifacts/cc/dd/faktura.txt", "faktura.txt")
    service, _, classifier = _service(
        _persisted_case(first, second),
        contents={
            "artifacts/aa/bb/message.txt": b"First body",
            "artifacts/cc/dd/faktura.txt": b"Second body",
        },
    )

    service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert classifier.seen_text is not None
    assert "--- ARTIFACT 0: message.txt ---" in classifier.seen_text
    assert "--- ARTIFACT 1: faktura.txt ---" in classifier.seen_text
    assert "artifacts/aa/bb" not in classifier.seen_text
    assert classifier.seen_text.index("First body") < classifier.seen_text.index("Second body")


def test_classify_case_returns_none_for_missing_case() -> None:
    service, _, _ = _service(None)

    result = service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert result is None


def test_classify_case_skips_when_classification_exists_without_force() -> None:
    existing = PersistedCaseClassification(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        category=CaseCategory.REQUEST,
        confidence=0.8,
        rationale="Existing classification",
        model_name="qwen2.5:7b",
        classified_at="2026-07-23T12:00:00+00:00",
    )
    service, _, classifier = _service(_persisted_case(), current_classification=existing)

    result = service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert result is not None
    assert result.skipped is True
    assert result.reason == "already_classified"
    assert classifier.calls == 0


def test_classify_case_force_replaces_existing_result() -> None:
    record = _text_record("artifacts/aa/bb/message.txt", "message.txt")
    existing = PersistedCaseClassification(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        category=CaseCategory.REQUEST,
        confidence=0.8,
        rationale="Existing classification",
        model_name="qwen2.5:7b",
        classified_at="2026-07-23T12:00:00+00:00",
    )
    service, repository, classifier = _service(
        _persisted_case(record),
        current_classification=existing,
        contents={"artifacts/aa/bb/message.txt": b"New body"},
    )

    result = service.classify_case(
        Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        force=True,
    )

    assert result is not None
    assert result.skipped is False
    assert repository.saved is not None
    assert repository.saved.category is CaseCategory.INVOICE
    assert classifier.calls == 1


def test_classify_case_returns_no_text_when_no_usable_text_exists() -> None:
    service, _, classifier = _service(_persisted_case())

    result = service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert result is not None
    assert result.skipped is True
    assert result.reason == "no_text"
    assert classifier.calls == 0


def test_classify_case_skips_unreadable_text_and_uses_remaining_artifacts() -> None:
    first = _text_record("artifacts/aa/bb/message.txt", "message.txt")
    second = _text_record("artifacts/cc/dd/faktura.txt", "faktura.txt")
    classifier = _FakeClassifier(
        result=CaseClassification(
            category=CaseCategory.INVOICE,
            confidence=0.92,
            rationale="Invoice-related content",
            model_name="qwen2.5:7b",
        )
    )
    classification_repository = _FakeClassificationRepository()
    service = CaseClassificationService(
        case_repository=_FakeCaseRepository(persisted_case=_persisted_case(first, second)),
        classification_repository=classification_repository,
        storage_reader=_FakeStorageReader(
            contents={
                "artifacts/aa/bb/message.txt": b"Broken",
                "artifacts/cc/dd/faktura.txt": b"Readable",
            },
            failing_locators={"artifacts/aa/bb/message.txt"},
        ),
        classifier=classifier,
        max_input_chars=100_000,
    )

    result = service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert result is not None
    assert result.skipped is False
    assert classifier.seen_text is not None
    assert "Readable" in classifier.seen_text
    assert "Broken" not in classifier.seen_text


def test_classify_case_returns_no_text_when_all_reads_fail() -> None:
    record = _text_record("artifacts/aa/bb/message.txt", "message.txt")
    classifier = _FakeClassifier(
        result=CaseClassification(
            category=CaseCategory.INVOICE,
            confidence=0.92,
            rationale="Invoice-related content",
            model_name="qwen2.5:7b",
        )
    )
    service = CaseClassificationService(
        case_repository=_FakeCaseRepository(persisted_case=_persisted_case(record)),
        classification_repository=_FakeClassificationRepository(),
        storage_reader=_FakeStorageReader(
            contents={"artifacts/aa/bb/message.txt": b"Broken"},
            failing_locators={"artifacts/aa/bb/message.txt"},
        ),
        classifier=classifier,
        max_input_chars=100_000,
    )

    result = service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert result is not None
    assert result.skipped is True
    assert result.reason == "no_text"
    assert classifier.calls == 0


def test_classify_case_truncates_input() -> None:
    record = _text_record("artifacts/aa/bb/message.txt", "message.txt")
    service, _, classifier = _service(
        _persisted_case(record),
        contents={"artifacts/aa/bb/message.txt": b"abcdef"},
        max_input_chars=3,
    )

    service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert classifier.seen_text is not None
    assert "NOTICE: The case content was truncated" in classifier.seen_text


def test_classify_case_does_not_save_when_model_fails() -> None:
    record = _text_record("artifacts/aa/bb/message.txt", "message.txt")
    service, repository, _ = _service(
        _persisted_case(record),
        contents={"artifacts/aa/bb/message.txt": b"Hello"},
        classifier=_FakeClassifier(
            result=CaseClassification(
                category=CaseCategory.INVOICE,
                confidence=0.92,
                rationale="Invoice-related content",
                model_name="qwen2.5:7b",
            ),
            exception=CaseClassificationError("boom"),
        ),
    )

    with pytest.raises(CaseClassificationError):
        service.classify_case(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert repository.saved is None
