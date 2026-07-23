from dataclasses import dataclass

from aioffice.application import CaseRepository, PersistedCase
from aioffice.application.services import CaseWorkspaceService
from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference


@dataclass(slots=True)
class _FakeCaseRepository(CaseRepository):
    persisted_case: PersistedCase | None

    def save(self, case: Case, reference_number: int) -> None:
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
        )
    )
    service = CaseWorkspaceService(repository=repository)

    workspace = service.get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.case_reference == "CASE-000001"
    assert workspace.status == "open"
    assert workspace.created_at == "2026-07-22T14:15:00+00:00"
    assert workspace.artifacts[0].artifact_type == "PDF"
    assert workspace.artifacts[0].locator == "artifacts/aa/bb/sample.pdf"
    assert workspace.history[0].title == "Imported"
    assert workspace.history[0].timestamp == "2026-07-22T14:15:00+00:00"


def test_case_workspace_service_returns_none_for_invalid_uuid() -> None:
    service = CaseWorkspaceService(repository=_FakeCaseRepository(persisted_case=None))

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
        )
    )
    service = CaseWorkspaceService(repository=repository)

    workspace = service.get_case_workspace("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert workspace is not None
    assert workspace.artifacts[0].artifact_type == "EMAIL"
    assert workspace.artifacts[0].locator == "artifacts/aa/bb/sample.eml"
