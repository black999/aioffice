from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from aioffice.application import (
    ArtifactRecord,
    ArtifactStorageReader,
    CaseRepository,
    DocumentExtractionError,
    DocumentStorage,
    DocumentTextExtractor,
    DownloadableArtifact,
    PersistedCase,
)
from aioffice.application.services import DocumentExtractionService
from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference


@dataclass(slots=True)
class _FakeRepository(CaseRepository):
    persisted_case: PersistedCase | None
    saved_records: tuple[ArtifactRecord, ...] | None = None
    save_calls: int = 0

    def save(
        self,
        case: Case,
        reference_number: int,
        artifact_records: tuple[ArtifactRecord, ...] | None = None,
    ) -> None:
        self.save_calls += 1
        if artifact_records is None:
            msg = "artifact_records are required in this test"
            raise AssertionError(msg)
        self.saved_records = artifact_records
        self.persisted_case = PersistedCase(
            case=case,
            reference_number=reference_number,
            status="open",
            created_at="2026-07-23T12:00:00+00:00",
            artifact_records=artifact_records,
        )

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

    def get_artifact(self, case_id: Identifier, position: int) -> DownloadableArtifact | None:
        persisted_case = self.get(case_id)
        if persisted_case is None:
            return None
        if position >= len(persisted_case.artifact_records):
            return None
        record = persisted_case.artifact_records[position]
        return DownloadableArtifact(
            case_id=case_id,
            position=position,
            artifact_type=record.artifact.artifact_type,
            storage_reference=record.artifact.storage_reference,
            display_name=record.display_name,
            content_type=record.content_type,
            source_position=record.source_position,
            is_truncated=record.is_truncated,
        )


@dataclass(slots=True)
class _FakeStorage(DocumentStorage):
    stored: list[tuple[str, bytes]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.stored is None:
            self.stored = []

    def store_file(self, source_path: Path) -> StorageReference:
        content = source_path.read_bytes()
        locator = f"artifacts/generated/{len(self.stored)}.txt"
        self.stored.append((locator, content))
        return StorageReference(storage_name="filesystem", locator=locator)


@dataclass(slots=True)
class _FakeStorageReader(ArtifactStorageReader):
    contents_by_locator: dict[str, bytes]
    failing_locators: set[str] | None = None

    def open_artifact(self, storage_reference: StorageReference):
        if self.failing_locators and storage_reference.locator in self.failing_locators:
            raise DocumentExtractionError("boom")
        return BytesIO(self.contents_by_locator[storage_reference.locator])

    def get_artifact_size(self, storage_reference: StorageReference) -> int:
        return len(self.contents_by_locator[storage_reference.locator])


@dataclass(frozen=True, slots=True)
class _FakeExtractor(DocumentTextExtractor):
    supported_suffixes: tuple[str, ...]
    results: dict[str, str | None]
    failing_locators: set[str] = ()

    def supports(self, artifact: DownloadableArtifact) -> bool:
        return artifact.display_name.lower().endswith(self.supported_suffixes)

    def extract_text(self, source) -> str | None:
        locator = source.name if hasattr(source, "name") else ""
        raise AssertionError(locator)


@dataclass(slots=True)
class _LocatorExtractor(DocumentTextExtractor):
    supported_suffixes: tuple[str, ...]
    results: dict[str, str | None]
    failing_locators: set[str] = ()

    def supports(self, artifact: DownloadableArtifact) -> bool:
        return artifact.display_name.lower().endswith(self.supported_suffixes)

    def extract_text(self, source: BytesIO) -> str | None:
        locator = source.getvalue().decode("utf-8")
        if locator in self.failing_locators:
            raise DocumentExtractionError("boom")
        return self.results[locator]


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


def _record(
    artifact_type: ArtifactType,
    locator: str,
    display_name: str,
    *,
    content_type: str | None,
    source_position: int | None = None,
    is_truncated: bool = False,
) -> ArtifactRecord:
    return ArtifactRecord(
        artifact=Artifact(
            artifact_type=artifact_type,
            storage_reference=StorageReference(storage_name="filesystem", locator=locator),
        ),
        display_name=display_name,
        content_type=content_type,
        source_position=source_position,
        is_truncated=is_truncated,
    )


def test_document_extraction_service_creates_text_for_pdf_and_docx() -> None:
    pdf_record = _record(ArtifactType.ATTACHMENT, "artifacts/source/pdf", "faktura.pdf", content_type="application/pdf")
    docx_record = _record(
        ArtifactType.ATTACHMENT,
        "artifacts/source/docx",
        "pismo.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    repository = _FakeRepository(persisted_case=_persisted_case(pdf_record, docx_record))
    storage = _FakeStorage()
    reader = _FakeStorageReader(
        contents_by_locator={
            "artifacts/source/pdf": b"pdf-source",
            "artifacts/source/docx": b"docx-source",
        }
    )
    extractor = _LocatorExtractor(
        supported_suffixes=(".pdf", ".docx"),
        results={"pdf-source": "PDF text", "docx-source": "DOCX text"},
    )
    service = DocumentExtractionService(
        repository=repository,
        storage=storage,
        storage_reader=reader,
        extractors=(extractor,),
        max_input_bytes=1024,
        max_output_chars=1000,
    )

    result = service.extract_case_documents(repository.persisted_case.case.id)  # type: ignore[union-attr]

    assert result == type(result)(extracted=2, skipped=0, failed=0)
    assert repository.saved_records is not None
    assert len(repository.saved_records) == 4
    assert repository.saved_records[2].source_position == 0
    assert repository.saved_records[3].source_position == 1
    assert repository.saved_records[2].display_name == "faktura.txt"
    assert repository.saved_records[3].display_name == "pismo.txt"
    assert storage.stored[0][1] == b"PDF text"
    assert storage.stored[1][1] == b"DOCX text"


def test_document_extraction_service_skips_documents_without_text_and_unsupported_types() -> None:
    pdf_record = _record(ArtifactType.ATTACHMENT, "artifacts/source/pdf", "faktura.pdf", content_type="application/pdf")
    unsupported = _record(
        ArtifactType.ATTACHMENT,
        "artifacts/source/bin",
        "blob.bin",
        content_type="application/octet-stream",
    )
    repository = _FakeRepository(persisted_case=_persisted_case(pdf_record, unsupported))
    storage = _FakeStorage()
    reader = _FakeStorageReader(contents_by_locator={"artifacts/source/pdf": b"pdf-source"})
    extractor = _LocatorExtractor(supported_suffixes=(".pdf",), results={"pdf-source": None})
    service = DocumentExtractionService(
        repository=repository,
        storage=storage,
        storage_reader=reader,
        extractors=(extractor,),
        max_input_bytes=1024,
        max_output_chars=1000,
    )

    result = service.extract_case_documents(repository.persisted_case.case.id)  # type: ignore[union-attr]

    assert result == type(result)(extracted=0, skipped=2, failed=0)
    assert repository.save_calls == 0
    assert storage.stored == []


def test_document_extraction_service_is_idempotent_per_source_position() -> None:
    source = _record(ArtifactType.ATTACHMENT, "artifacts/source/pdf", "faktura.pdf", content_type="application/pdf")
    existing_text = _record(
        ArtifactType.TEXT,
        "artifacts/generated/0.txt",
        "faktura.txt",
        content_type="text/plain; charset=utf-8",
        source_position=0,
    )
    repository = _FakeRepository(persisted_case=_persisted_case(source, existing_text))
    service = DocumentExtractionService(
        repository=repository,
        storage=_FakeStorage(),
        storage_reader=_FakeStorageReader(contents_by_locator={"artifacts/source/pdf": b"pdf-source"}),
        extractors=(_LocatorExtractor(supported_suffixes=(".pdf",), results={"pdf-source": "PDF text"}),),
        max_input_bytes=1024,
        max_output_chars=1000,
    )

    result = service.extract_case_documents(repository.persisted_case.case.id)  # type: ignore[union-attr]

    assert result == type(result)(extracted=0, skipped=1, failed=0)
    assert repository.save_calls == 0


def test_document_extraction_service_does_not_treat_email_body_text_as_duplicate() -> None:
    email_body = _record(
        ArtifactType.TEXT,
        "artifacts/body/message.txt",
        "message.txt",
        content_type="text/plain; charset=utf-8",
    )
    source = _record(ArtifactType.ATTACHMENT, "artifacts/source/pdf", "faktura.pdf", content_type="application/pdf")
    repository = _FakeRepository(persisted_case=_persisted_case(email_body, source))
    storage = _FakeStorage()
    service = DocumentExtractionService(
        repository=repository,
        storage=storage,
        storage_reader=_FakeStorageReader(contents_by_locator={"artifacts/source/pdf": b"pdf-source"}),
        extractors=(_LocatorExtractor(supported_suffixes=(".pdf",), results={"pdf-source": "PDF text"}),),
        max_input_bytes=1024,
        max_output_chars=1000,
    )

    result = service.extract_case_documents(repository.persisted_case.case.id)  # type: ignore[union-attr]

    assert result == type(result)(extracted=1, skipped=0, failed=0)
    assert repository.saved_records is not None
    assert repository.saved_records[2].source_position == 1


def test_document_extraction_service_marks_large_input_as_failed() -> None:
    source = _record(ArtifactType.ATTACHMENT, "artifacts/source/pdf", "faktura.pdf", content_type="application/pdf")
    repository = _FakeRepository(persisted_case=_persisted_case(source))
    reader = _FakeStorageReader(contents_by_locator={"artifacts/source/pdf": b"pdf-source"})
    service = DocumentExtractionService(
        repository=repository,
        storage=_FakeStorage(),
        storage_reader=reader,
        extractors=(_LocatorExtractor(supported_suffixes=(".pdf",), results={"pdf-source": "PDF text"}),),
        max_input_bytes=3,
        max_output_chars=1000,
    )

    result = service.extract_case_documents(repository.persisted_case.case.id)  # type: ignore[union-attr]

    assert result == type(result)(extracted=0, skipped=0, failed=1)
    assert repository.save_calls == 0


def test_document_extraction_service_continues_after_single_document_failure() -> None:
    broken = _record(ArtifactType.ATTACHMENT, "artifacts/source/one", "one.pdf", content_type="application/pdf")
    good = _record(ArtifactType.ATTACHMENT, "artifacts/source/two", "two.pdf", content_type="application/pdf")
    repository = _FakeRepository(persisted_case=_persisted_case(broken, good))
    storage = _FakeStorage()
    service = DocumentExtractionService(
        repository=repository,
        storage=storage,
        storage_reader=_FakeStorageReader(
            contents_by_locator={
                "artifacts/source/one": b"one-source",
                "artifacts/source/two": b"two-source",
            }
        ),
        extractors=(
            _LocatorExtractor(
                supported_suffixes=(".pdf",),
                results={"one-source": "broken", "two-source": "Two text"},
                failing_locators={"one-source"},
            ),
        ),
        max_input_bytes=1024,
        max_output_chars=1000,
    )

    result = service.extract_case_documents(repository.persisted_case.case.id)  # type: ignore[union-attr]

    assert result == type(result)(extracted=1, skipped=0, failed=1)
    assert repository.saved_records is not None
    assert repository.saved_records[-1].source_position == 1


def test_document_extraction_service_truncates_large_output_and_marks_record() -> None:
    source = _record(ArtifactType.ATTACHMENT, "artifacts/source/pdf", "faktura.pdf", content_type="application/pdf")
    repository = _FakeRepository(persisted_case=_persisted_case(source))
    storage = _FakeStorage()
    service = DocumentExtractionService(
        repository=repository,
        storage=storage,
        storage_reader=_FakeStorageReader(contents_by_locator={"artifacts/source/pdf": b"pdf-source"}),
        extractors=(_LocatorExtractor(supported_suffixes=(".pdf",), results={"pdf-source": "abcdef"}),),
        max_input_bytes=1024,
        max_output_chars=3,
    )

    result = service.extract_case_documents(repository.persisted_case.case.id)  # type: ignore[union-attr]

    assert result == type(result)(extracted=1, skipped=0, failed=0)
    assert repository.saved_records is not None
    assert repository.saved_records[-1].is_truncated is True
    assert storage.stored[-1][1] == b"abc"


def test_document_extraction_service_returns_none_for_missing_case() -> None:
    service = DocumentExtractionService(
        repository=_FakeRepository(persisted_case=None),
        storage=_FakeStorage(),
        storage_reader=_FakeStorageReader(contents_by_locator={}),
        extractors=(),
        max_input_bytes=1024,
        max_output_chars=1000,
    )

    assert service.extract_case_documents(Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")) is None
