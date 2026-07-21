from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference

import pytest


def test_case_starts_empty() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    assert case.artifacts == ()
    assert case.pending_events == ()


def test_case_adds_artifact_and_records_domain_event() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    artifact = Artifact(
        artifact_type=ArtifactType.EMAIL,
        storage_reference=StorageReference(storage_name="maildir", locator="inbox/message.eml"),
        id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )

    case.add_artifact(artifact)

    assert case.artifacts == (artifact,)
    assert len(case.pending_events) == 1
    assert case.pending_events[0].name == "case.artifact_added"
    assert dict(case.pending_events[0].payload) == {
        "case_id": str(case.id),
        "artifact_id": str(artifact.id),
        "artifact_type": "email",
    }


def test_case_rejects_duplicate_artifact() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    artifact = Artifact(
        artifact_type=ArtifactType.PDF,
        storage_reference=StorageReference(storage_name="files", locator="contracts/offer.pdf"),
        id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )
    case.add_artifact(artifact)

    with pytest.raises(ValueError, match="already assigned"):
        case.add_artifact(artifact)


def test_case_pull_events_returns_and_clears_pending_events() -> None:
    case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    artifact = Artifact(
        artifact_type=ArtifactType.TEXT,
        storage_reference=StorageReference(storage_name="ocr", locator="contracts/offer.txt"),
        id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )
    case.add_artifact(artifact)

    events = case.pull_events()

    assert len(events) == 1
    assert case.pending_events == ()
