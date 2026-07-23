from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from aioffice.application import (
    ArtifactLocatorConflictError,
    CaseFactory,
    CaseRepository,
    ImportedMailConflictError,
    ImportedMailRepository,
    MailContentParser,
    MailboxClient,
    MailboxMessage,
    ParsedAttachment,
    ParsedMailContent,
    PersistedCase,
)
from aioffice.application.services import MailImportService
from aioffice.domain import Artifact, ArtifactType, Case, Identifier
from aioffice.domain.storage import StorageReference
from aioffice.infrastructure import FilesystemStorage, SQLiteCaseRepository


@dataclass(slots=True)
class _FakeMailboxClient(MailboxClient):
    messages: tuple[MailboxMessage, ...]

    def list_messages(self) -> tuple[MailboxMessage, ...]:
        return self.messages


@dataclass(slots=True)
class _FakeImportedMailRepository(ImportedMailRepository):
    imported: set[tuple[str, str]] = field(default_factory=set)
    records: list[tuple[str, str, str | None, Identifier]] = field(default_factory=list)

    def has_imported(self, mailbox_identity: str, uid: str) -> bool:
        return (mailbox_identity, uid) in self.imported

    def save_import(
        self,
        mailbox_identity: str,
        uid: str,
        message_id: str | None,
        case_id: Identifier,
    ) -> None:
        key = (mailbox_identity, uid)
        if key in self.imported:
            raise ImportedMailConflictError("mailbox UID has already been imported")
        self.imported.add(key)
        self.records.append((mailbox_identity, uid, message_id, case_id))


@dataclass(slots=True)
class _CountingNumberProvider:
    next_value: int = 1
    calls: int = 0

    def next_number(self) -> int:
        value = self.next_value
        self.next_value += 1
        self.calls += 1
        return value


@dataclass(slots=True)
class _ConflictCaseRepository(CaseRepository):
    persisted_case: PersistedCase
    get_calls: int = 0

    def save(self, case: Case, reference_number: int) -> None:
        raise ArtifactLocatorConflictError("artifact locator is already assigned to another case")

    def get(self, case_id: Identifier) -> PersistedCase | None:
        if self.persisted_case.case.id == case_id:
            return self.persisted_case
        return None

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        self.get_calls += 1
        if self.get_calls == 1:
            return None
        return self.persisted_case

    def list(self) -> tuple[PersistedCase, ...]:
        return (self.persisted_case,)

    def count(self) -> int:
        return 1


@dataclass(slots=True)
class _FakeMailContentParser(MailContentParser):
    parsed_content: ParsedMailContent = ParsedMailContent(body_text="Body", attachments=())
    exception: Exception | None = None
    calls: int = 0

    def parse(self, raw_message: bytes) -> ParsedMailContent:
        self.calls += 1
        if self.exception is not None:
            raise self.exception
        return self.parsed_content


@dataclass(slots=True)
class _FailingStorage:
    delegate: FilesystemStorage
    failing_suffix: str

    def store_file(self, source_path: Path) -> StorageReference:
        if source_path.suffix.lower() == self.failing_suffix:
            raise RuntimeError("boom")
        return self.delegate.store_file(source_path)


def _message(uid: str, raw_message: bytes, message_id: str | None = None) -> MailboxMessage:
    return MailboxMessage(
        mailbox_identity="imap.example.com/user@example.com/INBOX",
        uid=uid,
        message_id=message_id,
        subject="Subject",
        sender="sender@example.com",
        received_at=datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
        raw_message=raw_message,
    )


def _service(
    tmp_path: Path,
    messages: tuple[MailboxMessage, ...],
    *,
    parser: _FakeMailContentParser | None = None,
    attachment_limit_bytes: int = 25 * 1024 * 1024,
    attachment_limit_count: int = 50,
) -> tuple[
    MailImportService,
    SQLiteCaseRepository,
    _FakeImportedMailRepository,
    _CountingNumberProvider,
    _FakeMailContentParser,
]:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    imported_mail_repository = _FakeImportedMailRepository()
    provider = _CountingNumberProvider()
    fake_parser = parser or _FakeMailContentParser()
    service = MailImportService(
        mailbox_client=_FakeMailboxClient(messages=messages),
        imported_mail_repository=imported_mail_repository,
        storage=FilesystemStorage(root_directory=tmp_path),
        case_factory=CaseFactory(),
        case_repository=repository,
        case_number_provider=provider,
        mail_content_parser=fake_parser,
        imap_max_attachment_bytes=attachment_limit_bytes,
        imap_max_attachments_per_message=attachment_limit_count,
    )
    return service, repository, imported_mail_repository, provider, fake_parser


def test_mail_import_creates_email_and_text_artifacts(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(parsed_content=ParsedMailContent(body_text="Hello body", attachments=()))
    service, repository, imported_mail_repository, provider, _ = _service(
        tmp_path,
        (_message("1", b"raw message"),),
        parser=parser,
    )

    result = service.import_new_messages()
    persisted_cases = repository.list()

    assert result.imported == 1
    assert result.skipped == 0
    assert result.failed == 0
    assert repository.count() == 1
    assert provider.calls == 1
    assert len(imported_mail_repository.records) == 1
    assert tuple(artifact.artifact_type for artifact in persisted_cases[0].case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.TEXT,
    )
    assert persisted_cases[0].case.artifacts[1].storage_reference.locator.endswith(".txt")
    repository.close()


def test_mail_import_creates_email_text_and_attachment_artifacts(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(
        parsed_content=ParsedMailContent(
            body_text="Hello body",
            attachments=(
                ParsedAttachment(filename="invoice.pdf", content_type="application/pdf", payload=b"PDF"),
            ),
        )
    )
    service, repository, _, _, _ = _service(tmp_path, (_message("1", b"raw message"),), parser=parser)

    result = service.import_new_messages()
    persisted_case = repository.list()[0]

    assert result.imported == 1
    assert tuple(artifact.artifact_type for artifact in persisted_case.case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.TEXT,
        ArtifactType.ATTACHMENT,
    )
    assert persisted_case.case.artifacts[2].storage_reference.locator.endswith(".pdf")
    repository.close()


def test_mail_import_preserves_attachment_order(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(
        parsed_content=ParsedMailContent(
            body_text="Hello body",
            attachments=(
                ParsedAttachment(filename="one.txt", content_type="text/plain", payload=b"one"),
                ParsedAttachment(filename="two.bin", content_type="application/octet-stream", payload=b"two"),
            ),
        )
    )
    service, repository, _, _, _ = _service(tmp_path, (_message("1", b"raw message"),), parser=parser)

    service.import_new_messages()
    persisted_case = repository.list()[0]

    assert tuple(artifact.artifact_type for artifact in persisted_case.case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.TEXT,
        ArtifactType.ATTACHMENT,
        ArtifactType.ATTACHMENT,
    )
    assert persisted_case.case.artifacts[2].storage_reference.locator.endswith(".txt")
    assert persisted_case.case.artifacts[3].storage_reference.locator.endswith(".bin")
    repository.close()


def test_mail_import_without_body_creates_only_email_and_attachments(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(
        parsed_content=ParsedMailContent(
            body_text=None,
            attachments=(
                ParsedAttachment(filename="invoice.pdf", content_type="application/pdf", payload=b"PDF"),
            ),
        )
    )
    service, repository, _, _, _ = _service(tmp_path, (_message("1", b"raw message"),), parser=parser)

    service.import_new_messages()
    persisted_case = repository.list()[0]

    assert tuple(artifact.artifact_type for artifact in persisted_case.case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.ATTACHMENT,
    )
    repository.close()


def test_mail_import_skips_same_uid_without_consuming_number(tmp_path: Path) -> None:
    message = _message("1", b"raw message")
    service, repository, imported_mail_repository, provider, _ = _service(tmp_path, (message,))

    first_result = service.import_new_messages()
    second_result = service.import_new_messages()

    assert first_result.imported == 1
    assert second_result.imported == 0
    assert second_result.skipped == 1
    assert repository.count() == 1
    assert provider.calls == 1
    assert len(imported_mail_repository.records) == 1
    repository.close()


def test_mail_import_reuses_existing_case_for_identical_eml_without_recreating_artifacts(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(
        parsed_content=ParsedMailContent(
            body_text="Hello body",
            attachments=(
                ParsedAttachment(filename="invoice.pdf", content_type="application/pdf", payload=b"PDF"),
            ),
        )
    )
    raw_message = b"same eml"
    service, repository, imported_mail_repository, provider, fake_parser = _service(
        tmp_path,
        (
            _message("1", raw_message, "<one@example.com>"),
            _message("2", raw_message, "<two@example.com>"),
        ),
        parser=parser,
    )

    result = service.import_new_messages()
    persisted_case = repository.list()[0]

    assert result.imported == 2
    assert repository.count() == 1
    assert provider.calls == 1
    assert fake_parser.calls == 1
    assert len(imported_mail_repository.records) == 2
    assert tuple(artifact.artifact_type for artifact in persisted_case.case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.TEXT,
        ArtifactType.ATTACHMENT,
    )
    artifact_paths = list((tmp_path / "artifacts").rglob("*"))
    stored_files = [path for path in artifact_paths if path.is_file()]
    assert len(stored_files) == 3
    repository.close()


def test_mail_import_parser_error_marks_message_as_failed(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(exception=RuntimeError("parse failed"))
    service, repository, imported_mail_repository, provider, _ = _service(
        tmp_path,
        (_message("1", b"raw message"),),
        parser=parser,
    )

    result = service.import_new_messages()

    assert result.imported == 0
    assert result.failed == 1
    assert repository.count() == 0
    assert provider.calls == 0
    assert imported_mail_repository.records == []
    repository.close()


def test_mail_import_attachment_storage_error_does_not_save_case_or_import_record(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(
        parsed_content=ParsedMailContent(
            body_text="Hello body",
            attachments=(
                ParsedAttachment(filename="invoice.pdf", content_type="application/pdf", payload=b"PDF"),
            ),
        )
    )
    service, repository, imported_mail_repository, provider, _ = _service(
        tmp_path,
        (_message("1", b"raw message"),),
        parser=parser,
    )
    service.storage = _FailingStorage(delegate=FilesystemStorage(root_directory=tmp_path), failing_suffix=".pdf")

    result = service.import_new_messages()

    assert result.imported == 0
    assert result.failed == 1
    assert repository.count() == 0
    assert provider.calls == 0
    assert imported_mail_repository.records == []
    repository.close()


def test_mail_import_rejects_attachment_size_limit(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(
        parsed_content=ParsedMailContent(
            body_text="Hello body",
            attachments=(
                ParsedAttachment(filename="large.bin", content_type="application/octet-stream", payload=b"x" * 11),
            ),
        )
    )
    service, repository, imported_mail_repository, provider, _ = _service(
        tmp_path,
        (_message("1", b"raw message"),),
        parser=parser,
        attachment_limit_bytes=10,
    )

    result = service.import_new_messages()

    assert result.imported == 0
    assert result.failed == 1
    assert repository.count() == 0
    assert provider.calls == 0
    assert imported_mail_repository.records == []
    repository.close()


def test_mail_import_rejects_attachment_count_limit(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(
        parsed_content=ParsedMailContent(
            body_text="Hello body",
            attachments=(
                ParsedAttachment(filename="one.bin", content_type="application/octet-stream", payload=b"1"),
                ParsedAttachment(filename="two.bin", content_type="application/octet-stream", payload=b"2"),
            ),
        )
    )
    service, repository, imported_mail_repository, provider, _ = _service(
        tmp_path,
        (_message("1", b"raw message"),),
        parser=parser,
        attachment_limit_count=1,
    )

    result = service.import_new_messages()

    assert result.imported == 0
    assert result.failed == 1
    assert repository.count() == 0
    assert provider.calls == 0
    assert imported_mail_repository.records == []
    repository.close()


def test_mail_import_does_not_save_import_record_after_failed_case_save(tmp_path: Path) -> None:
    raw_message = b"same eml"
    storage = FilesystemStorage(root_directory=tmp_path)
    existing_source = tmp_path / "existing.eml"
    existing_source.write_bytes(raw_message)
    storage_reference = storage.store_file(existing_source)
    existing_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    existing_case.add_artifact(Artifact(artifact_type=ArtifactType.EMAIL, storage_reference=storage_reference))
    persisted_case = PersistedCase(
        case=existing_case,
        reference_number=1,
        status="open",
        created_at="2026-07-23T12:00:00+00:00",
    )
    imported_mail_repository = _FakeImportedMailRepository()
    provider = _CountingNumberProvider()
    parser = _FakeMailContentParser(parsed_content=ParsedMailContent(body_text="Hello body", attachments=()))
    service = MailImportService(
        mailbox_client=_FakeMailboxClient(messages=(_message("2", raw_message, "<two@example.com>"),)),
        imported_mail_repository=imported_mail_repository,
        storage=storage,
        case_factory=CaseFactory(),
        case_repository=_ConflictCaseRepository(persisted_case=persisted_case),
        case_number_provider=provider,
        mail_content_parser=parser,
    )

    result = service.import_new_messages()

    assert result.imported == 1
    assert result.failed == 0
    assert provider.calls == 1
    assert len(imported_mail_repository.records) == 1


def test_mail_import_persists_email_text_and_attachment_types_after_repository_reopen(tmp_path: Path) -> None:
    parser = _FakeMailContentParser(
        parsed_content=ParsedMailContent(
            body_text="Hello body",
            attachments=(
                ParsedAttachment(filename="invoice.pdf", content_type="application/pdf", payload=b"PDF"),
            ),
        )
    )
    service, repository, imported_mail_repository, provider, _ = _service(
        tmp_path,
        (_message("1", b"raw message", "<one@example.com>"),),
        parser=parser,
    )

    result = service.import_new_messages()

    assert result.imported == 1
    repository.close()

    reloaded_repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    persisted_cases = reloaded_repository.list()

    assert len(persisted_cases) == 1
    assert tuple(artifact.artifact_type for artifact in persisted_cases[0].case.artifacts) == (
        ArtifactType.EMAIL,
        ArtifactType.TEXT,
        ArtifactType.ATTACHMENT,
    )
    assert persisted_cases[0].case.artifacts[0].storage_reference.locator.endswith(".eml")
    assert persisted_cases[0].case.artifacts[1].storage_reference.locator.endswith(".txt")
    assert persisted_cases[0].case.artifacts[2].storage_reference.locator.endswith(".pdf")
    assert len(imported_mail_repository.records) == 1
    assert provider.calls == 1
    reloaded_repository.close()
