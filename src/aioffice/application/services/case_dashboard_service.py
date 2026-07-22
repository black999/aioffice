"""Read-only application service for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from aioffice.application import CaseRepository
from aioffice.application.case_numbers import format_case_reference


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """Minimal read model for displaying a case."""

    case_id: str
    case_reference: str
    status: str


@dataclass(slots=True)
class CaseDashboardService:
    """Provide read-only case data for the web interface."""

    repository: CaseRepository

    def list_cases(self) -> tuple[CaseSummary, ...]:
        """Return cases formatted for dashboard rendering."""

        return tuple(
            CaseSummary(
                case_id=str(persisted_case.case.id),
                case_reference=format_case_reference(persisted_case.reference_number),
                status=persisted_case.status,
            )
            for persisted_case in self.repository.list()
        )

    def count_cases(self) -> int:
        """Return the total number of persisted cases."""

        return self.repository.count()
