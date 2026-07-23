from dataclasses import dataclass
from io import BytesIO

from aioffice.application import ArtifactRecord, CaseRepository, PersistedCase
from aioffice.application.services import CaseWorkspaceService
from aioffice.application.storage import ArtifactNotFoundError, ArtifactStorageReader
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
        if self.persisted_case is None:
            return None
        if self.persisted_case.case.id != case_id:
            return None
        return self.persisted_case

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        if self.persisted_case is None:
            return None
        if not self.persisted_case.case.artifacts:
            return None
        if self.persisted_case.case.artifacts[0].storage_reference.locator != locator:
            return None
        return self.persisted_case

    def list(self) -> tuple[PersistedCase, ...]:
        if self.persisted_case is None:
            return ()
        return (self.persisted_case,)

    def count(self) -> int:
        return 0 if self.persisted_case is None else 1

    def get_artifact(self, case_id: Identifier, position: int):
        msg = "get_artifact is not used in this test"
        raise NotImplementedError(msg)


@dataclass(slots=True)
class _FakeStorageReader(ArtifactStorageReader):
    contents_by_locator: dict[str, bytes]
    failing_locators: set[str] | None = None

    def open_artifact(self, storage_reference: StorageReference):
        if self.failing_locators and storage_reference.locator in self.failing_locators:
            raise ArtifactNotFoundError("missing")
        return BytesIO(self.contents_by_locator[storage_reference.locator])

    def get_artifact_size(self, storage_reference: StorageReference) -> int:
        return len(self.contents_by_locator[storage_reference.locator])


def test_case_workspace_service_returns_read_model() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/sample.pdf",
            ),
        )
    )
    repository = _FakeCaseRepository(
        persisted_case=PersistedCase(
            case=case,
            reference_number=1,
            status="open",
            created_at="2026-07-22T14:15:00+00:00",
            artifact_records=(
                ArtifactRecord(
                    artifact=case.artifacts[0],
                    display_name="sample.pdf",
                    content_type="application/pdf",
                ),
            ),
        )
    )
    service = CaseWorkspaceService(repository=repository, storage_reader=_FakeStorageReader(contents_by_locator={}))

    workspace = service.get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.case_reference == "CASE-000001"
    assert workspace.status == "open"
    assert workspace.created_at == "2026-07-22T14:15:00+00:00"
    assert workspace.email_body is None
    assert workspace.artifacts[0].artifact_type == "PDF"
    assert workspace.artifacts[0].display_name == "sample.pdf"
    assert workspace.artifacts[0].download_url == "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifacts/0/download"
    assert workspace.artifacts[0].source_position is None
    assert workspace.artifacts[0].is_truncated is False
    assert workspace.history[0].title == "Imported"
    assert workspace.history[0].timestamp == "2026-07-22T14:15:00+00:00"


def test_case_workspace_service_returns_none_for_invalid_uuid() -> None:
    service = CaseWorkspaceService(
        repository=_FakeCaseRepository(persisted_case=None),
        storage_reader=_FakeStorageReader(contents_by_locator={}),
    )

    workspace = service.get_case_workspace("not-a-uuid")

    assert workspace is None


def test_case_workspace_service_returns_email_artifact_label() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/sample.eml",
            ),
        )
    )
    repository = _FakeCaseRepository(
        persisted_case=PersistedCase(
            case=case,
            reference_number=1,
            status="open",
            created_at="2026-07-23T14:15:00+00:00",
            artifact_records=(
                ArtifactRecord(
                    artifact=case.artifacts[0],
                    display_name="sample.eml",
                    content_type="message/rfc822",
                ),
            ),
        )
    )
    service = CaseWorkspaceService(repository=repository, storage_reader=_FakeStorageReader(contents_by_locator={}))

    workspace = service.get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.artifacts[0].artifact_type == "EMAIL"
    assert workspace.artifacts[0].display_name == "sample.eml"


def test_case_workspace_service_returns_all_artifact_labels_in_order() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.EMAIL,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/sample.eml",
            ),
        )
    )
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/sample.txt",
            ),
        )
    )
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.ATTACHMENT,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/attachment.pdf",
            ),
        )
    )
    repository = _FakeCaseRepository(
        persisted_case=PersistedCase(
            case=case,
            reference_number=1,
            status="open",
            created_at="2026-07-23T14:15:00+00:00",
            artifact_records=(
                ArtifactRecord(
                    artifact=case.artifacts[0],
                    display_name="sample.eml",
                    content_type="message/rfc822",
                ),
                ArtifactRecord(
                    artifact=case.artifacts[1],
                    display_name="sample.txt",
                    content_type="text/plain; charset=utf-8",
                ),
                ArtifactRecord(
                    artifact=case.artifacts[2],
                    display_name="attachment.pdf",
                    content_type="application/pdf",
                ),
            ),
        )
    )
    service = CaseWorkspaceService(
        repository=repository,
        storage_reader=_FakeStorageReader(contents_by_locator={"artifacts/aa/bb/sample.txt": b"Hello\nWorld"}),
    )

    workspace = service.get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert tuple(artifact.artifact_type for artifact in workspace.artifacts) == (
        "EMAIL",
        "TEXT",
        "ATTACHMENT",
    )
    assert workspace.email_body == "Hello\nWorld"


def test_case_workspace_service_returns_none_body_when_text_artifact_is_missing() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/sample.pdf",
            ),
        )
    )
    repository = _FakeCaseRepository(
        persisted_case=PersistedCase(
            case=case,
            reference_number=1,
            status="open",
            created_at="2026-07-23T14:15:00+00:00",
            artifact_records=(
                ArtifactRecord(
                    artifact=case.artifacts[0],
                    display_name="sample.pdf",
                    content_type="application/pdf",
                ),
            ),
        )
    )

    workspace = CaseWorkspaceService(
        repository=repository,
        storage_reader=_FakeStorageReader(contents_by_locator={}),
    ).get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.email_body is None
    assert workspace.email_body_truncated is False
    assert workspace.email_body_error is False


def test_case_workspace_service_decodes_invalid_utf8_with_replacement() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/sample.txt",
            ),
        )
    )
    repository = _FakeCaseRepository(
        persisted_case=PersistedCase(
            case=case,
            reference_number=1,
            status="open",
            created_at="2026-07-23T14:15:00+00:00",
            artifact_records=(
                ArtifactRecord(
                    artifact=case.artifacts[0],
                    display_name="sample.txt",
                    content_type="text/plain; charset=utf-8",
                ),
            ),
        )
    )

    workspace = CaseWorkspaceService(
        repository=repository,
        storage_reader=_FakeStorageReader(contents_by_locator={"artifacts/aa/bb/sample.txt": b"abc\xffdef"}),
    ).get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.email_body == "abc\ufffddef"


def test_case_workspace_service_marks_large_text_as_truncated() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/sample.txt",
            ),
        )
    )
    repository = _FakeCaseRepository(
        persisted_case=PersistedCase(
            case=case,
            reference_number=1,
            status="open",
            created_at="2026-07-23T14:15:00+00:00",
            artifact_records=(
                ArtifactRecord(
                    artifact=case.artifacts[0],
                    display_name="sample.txt",
                    content_type="text/plain; charset=utf-8",
                ),
            ),
        )
    )

    workspace = CaseWorkspaceService(
        repository=repository,
        storage_reader=_FakeStorageReader(contents_by_locator={"artifacts/aa/bb/sample.txt": b"abcdef"}),
        email_body_max_bytes=3,
    ).get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.email_body == "abc"
    assert workspace.email_body_truncated is True
    assert workspace.email_body_error is False


def test_case_workspace_service_body_read_error_does_not_fail_workspace() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    case.add_artifact(
        Artifact(
            artifact_type=ArtifactType.TEXT,
            storage_reference=StorageReference(
                storage_name="filesystem",
                locator="artifacts/aa/bb/sample.txt",
            ),
        )
    )
    repository = _FakeCaseRepository(
        persisted_case=PersistedCase(
            case=case,
            reference_number=1,
            status="open",
            created_at="2026-07-23T14:15:00+00:00",
            artifact_records=(
                ArtifactRecord(
                    artifact=case.artifacts[0],
                    display_name="sample.txt",
                    content_type="text/plain; charset=utf-8",
                ),
            ),
        )
    )

    workspace = CaseWorkspaceService(
        repository=repository,
        storage_reader=_FakeStorageReader(
            contents_by_locator={},
            failing_locators={"artifacts/aa/bb/sample.txt"},
        ),
    ).get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.email_body is None
    assert workspace.email_body_error is True
