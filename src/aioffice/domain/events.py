"""Domain event primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Immutable record of a domain-relevant fact."""

    name: str
    payload: Mapping[str, object] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "name must not be empty"
            raise ValueError(msg)
        if self.occurred_at.tzinfo is None:
            msg = "occurred_at must be timezone-aware"
            raise ValueError(msg)
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
