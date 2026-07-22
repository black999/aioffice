from aioffice.application import CaseFactory, InMemoryCaseRegistry
from aioffice.domain import Artifact, ArtifactType, Identifier, StorageReference


def test_case_factory_creates_case_with_artifact() -> None:
    artifact = Artifact(
        artifact_type=ArtifactType.PDF,
        storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    case = CaseFactory().create_from_artifact(artifact)

    assert case.artifacts == (artifact,)


def test_in_memory_case_registry_count_reflects_added_cases() -> None:
    registry = InMemoryCaseRegistry()
    first_case = CaseFactory().create_from_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/aa/bb/file.pdf"),
        )
    )
    second_case = CaseFactory().create_from_artifact(
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=StorageReference(storage_name="filesystem", locator="artifacts/cc/dd/file.pdf"),
        )
    )

    registry.add(first_case)
    registry.add(second_case)

    assert registry.count() == 2
    assert registry.get(first_case.id) is first_case
    assert registry.list() == (first_case, second_case)
