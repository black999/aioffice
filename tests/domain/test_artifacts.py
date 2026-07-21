from datetime import datetime

import pytest

from aioffice.domain import Artifact, ArtifactType, Identifier, StorageReference


def test_artifact_preserves_values() -> None:
    reference = StorageReference(storage_name="files", locator="contracts/offer.pdf")
    identifier = Identifier.from_string("12345678-1234-5678-1234-567812345678")

    artifact = Artifact(
        artifact_type=ArtifactType.PDF,
        storage_reference=reference,
        id=identifier,
    )

    assert artifact.artifact_type is ArtifactType.PDF
    assert artifact.id is identifier
    assert artifact.storage_reference is reference


def test_artifact_requires_timezone_aware_creation_timestamp() -> None:
    reference = StorageReference(storage_name="files", locator="contracts/offer.pdf")

    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        Artifact(
            artifact_type=ArtifactType.PDF,
            storage_reference=reference,
            created_at=datetime(2026, 7, 21, 12, 0, 0),
        )


def test_artifact_type_values_match_domain_language() -> None:
    assert ArtifactType.EMAIL.value == "email"
    assert ArtifactType.PDF.value == "pdf"
    assert ArtifactType.TEXT.value == "text"
