"""Case number abstractions and formatting."""

from __future__ import annotations

from typing import Protocol


class CaseNumberProvider(Protocol):
    """Allocate business reference numbers for cases."""

    def next_number(self) -> int:
        """Return the next unique business case number."""


def format_case_reference(number: int) -> str:
    """Format an integer case number for presentation."""

    return f"CASE-{number:06d}"
