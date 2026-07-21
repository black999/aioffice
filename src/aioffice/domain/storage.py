"""Storage-related value objects for the domain layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StorageReference:
    """Logical pointer to content stored outside the domain model."""

    storage_name: str
    locator: str

    def __post_init__(self) -> None:
        if not self.storage_name.strip():
            msg = "storage_name must not be empty"
            raise ValueError(msg)
        if not self.locator.strip():
            msg = "locator must not be empty"
            raise ValueError(msg)
