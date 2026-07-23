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
    MailboxClient,
    MailboxMessage,
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
class _FailingStorage:
    delegate: FilesystemStorage

    def store_file(self, source_path: Path) -> StorageReference:
        if source_path.read_bytes() == b"broken":
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
) -> tuple[MailImportService, SQLiteCaseRepository, _FakeImportedMailRepository, _CountingNumberProvider]:
    repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    imported_mail_repository = _FakeImportedMailRepository()
    provider = _CountingNumberProvider()
    service = MailImportService(
        mailbox_client=_FakeMailboxClient(messages=messages),
        imported_mail_repository=imported_mail_repository,
        storage=FilesystemStorage(root_directory=tmp_path),
        case_factory=CaseFactory(),
        case_repository=repository,
        case_number_provider=provider,
    )
    return service, repository, imported_mail_repository, provider


def test_mail_import_creates_case_for_one_message(tmp_path: Path) -> None:
    service, repository, imported_mail_repository, provider = _service(
        tmp_path,
        (_message("1", b"From: sender@example.com\r\nSubject: One\r\n\r\nhello"),),
    )

    result = service.import_new_messages()

    assert result.imported == 1
    assert result.skipped == 0
    assert result.failed == 0
    assert repository.count() == 1
    assert provider.calls == 1
    assert len(imported_mail_repository.records) == 1
    artifact_paths = list((tmp_path / "artifacts").rglob("*.eml"))
    assert len(artifact_paths) == 1
    repository.close()


def test_mail_import_skips_same_uid_on_second_run_without_consuming_number(tmp_path: Path) -> None:
    message = _message("1", b"From: sender@example.com\r\nSubject: One\r\n\r\nhello")
    service, repository, imported_mail_repository, provider = _service(tmp_path, (message,))

    first_result = service.import_new_messages()
    second_result = service.import_new_messages()

    assert first_result.imported == 1
    assert second_result.imported == 0
    assert second_result.skipped == 1
    assert repository.count() == 1
    assert provider.calls == 1
    assert len(imported_mail_repository.records) == 1
    repository.close()


def test_mail_import_creates_two_cases_for_different_uids_and_content(tmp_path: Path) -> None:
    service, repository, imported_mail_repository, provider = _service(
        tmp_path,
        (
            _message("1", b"From: sender@example.com\r\nSubject: One\r\n\r\nfirst"),
            _message("2", b"From: sender@example.com\r\nSubject: Two\r\n\r\nsecond"),
        ),
    )

    result = service.import_new_messages()

    assert result.imported == 2
    assert repository.count() == 2
    assert provider.calls == 2
    assert len(imported_mail_repository.records) == 2
    repository.close()


def test_mail_import_reuses_existing_case_for_identical_content_with_different_uids(tmp_path: Path) -> None:
    raw_message = b"From: sender@example.com\r\nSubject: Same\r\n\r\nbody"
    service, repository, imported_mail_repository, provider = _service(
        tmp_path,
        (
            _message("1", raw_message, "<one@example.com>"),
            _message("2", raw_message, "<two@example.com>"),
        ),
    )

    result = service.import_new_messages()

    assert result.imported == 2
    assert repository.count() == 1
    assert provider.calls == 1
    assert len(imported_mail_repository.records) == 2
    assert imported_mail_repository.records[0][3] == imported_mail_repository.records[1][3]
    artifact_paths = list((tmp_path / "artifacts").rglob("*.eml"))
    assert len(artifact_paths) == 1
    repository.close()


def test_mail_import_continues_after_one_message_failure(tmp_path: Path) -> None:
    service, repository, imported_mail_repository, provider = _service(
        tmp_path,
        (
            _message("1", b"broken", "<broken@example.com>"),
            _message("2", b"From: sender@example.com\r\nSubject: Two\r\n\r\nsecond", "<ok@example.com>"),
        ),
    )
    service.storage = _FailingStorage(delegate=FilesystemStorage(root_directory=tmp_path))

    result = service.import_new_messages()

    assert result.imported == 1
    assert result.failed == 1
    assert result.skipped == 0
    assert repository.count() == 1
    assert provider.calls == 1
    assert len(imported_mail_repository.records) == 1
    assert imported_mail_repository.records[0][1] == "2"
    repository.close()


def test_mail_import_does_not_save_import_record_after_failed_case_save(tmp_path: Path) -> None:
    raw_message = b"From: sender@example.com\r\nSubject: Same\r\n\r\nbody"
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
    service = MailImportService(
        mailbox_client=_FakeMailboxClient(messages=(_message("2", raw_message, "<two@example.com>"),)),
        imported_mail_repository=imported_mail_repository,
        storage=storage,
        case_factory=CaseFactory(),
        case_repository=_ConflictCaseRepository(persisted_case=persisted_case),
        case_number_provider=provider,
    )

    result = service.import_new_messages()

    assert result.imported == 1
    assert result.failed == 0
    assert provider.calls == 1
    assert len(imported_mail_repository.records) == 1


def test_mail_import_persists_email_artifact_type_after_repository_reopen(tmp_path: Path) -> None:
    service, repository, imported_mail_repository, provider = _service(
        tmp_path,
        (_message("1", b"From: sender@example.com\r\nSubject: One\r\n\r\nhello", "<one@example.com>"),),
    )

    result = service.import_new_messages()

    assert result.imported == 1
    repository.close()

    reloaded_repository = SQLiteCaseRepository(database_path=tmp_path / "storage" / "aioffice.db")
    persisted_cases = reloaded_repository.list()

    assert len(persisted_cases) == 1
    assert persisted_cases[0].case.artifacts[0].artifact_type is ArtifactType.EMAIL
    assert persisted_cases[0].case.artifacts[0].storage_reference.locator.endswith(".eml")
    assert len(imported_mail_repository.records) == 1
    assert provider.calls == 1
    reloaded_repository.close()
