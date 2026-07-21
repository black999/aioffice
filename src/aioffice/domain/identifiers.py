"""Identifier value object for domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class Identifier:
    """Stable domain identifier wrapper."""

    value: UUID = field(default_factory=uuid4)

    @classmethod
    def new(cls) -> Identifier:
        return cls()

    @classmethod
    def from_string(cls, value: str) -> Identifier:
        return cls(value=UUID(value))

    def __str__(self) -> str:
        return str(self.value)
