from uuid import UUID

from aioffice.domain import Identifier


def test_identifier_generates_uuid_by_default() -> None:
    identifier = Identifier()

    assert isinstance(identifier.value, UUID)


def test_identifier_can_be_created_from_string() -> None:
    identifier = Identifier.from_string("12345678-1234-5678-1234-567812345678")

    assert identifier.value == UUID("12345678-1234-5678-1234-567812345678")


def test_identifier_string_representation_matches_wrapped_uuid() -> None:
    identifier = Identifier.from_string("12345678-1234-5678-1234-567812345678")

    assert str(identifier) == "12345678-1234-5678-1234-567812345678"
