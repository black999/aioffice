from datetime import UTC, datetime

import pytest

from aioffice.domain import DomainEvent


def test_domain_event_requires_non_empty_name() -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        DomainEvent(name=" ")


def test_domain_event_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        DomainEvent(name="artifact.created", occurred_at=datetime(2026, 7, 21, 12, 0, 0))


def test_domain_event_freezes_payload_copy() -> None:
    payload = {"artifact_id": "123"}
    event = DomainEvent(
        name="artifact.created",
        payload=payload,
        occurred_at=datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC),
    )

    payload["artifact_id"] = "456"

    assert dict(event.payload) == {"artifact_id": "123"}


def test_domain_event_uses_utc_timestamp_by_default() -> None:
    event = DomainEvent(name="artifact.created")

    assert event.occurred_at.tzinfo is UTC
