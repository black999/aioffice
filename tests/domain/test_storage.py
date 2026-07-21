from aioffice.domain import StorageReference

import pytest


def test_storage_reference_requires_non_empty_storage_name() -> None:
    with pytest.raises(ValueError, match="storage_name must not be empty"):
        StorageReference(storage_name=" ", locator="inbox/message.eml")


def test_storage_reference_requires_non_empty_locator() -> None:
    with pytest.raises(ValueError, match="locator must not be empty"):
        StorageReference(storage_name="maildir", locator=" ")


def test_storage_reference_keeps_valid_values() -> None:
    reference = StorageReference(storage_name="maildir", locator="inbox/message.eml")

    assert reference.storage_name == "maildir"
    assert reference.locator == "inbox/message.eml"
