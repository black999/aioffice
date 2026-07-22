"""Read-only application service for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from aioffice.application import CaseRepository


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """Minimal read model for displaying a case."""

    case_id: str
    status: str


@dataclass(slots=True)
class CaseDashboardService:
    """Provide read-only case data for the web interface."""

    repository: CaseRepository
    default_status: str = "open"

    def list_cases(self) -> tuple[CaseSummary, ...]:
        """Return cases formatted for dashboard rendering."""

        return tuple(
            CaseSummary(case_id=str(case.id), status=self.default_status)
            for case in self.repository.list()
        )

    def count_cases(self) -> int:
        """Return the total number of persisted cases."""

        return self.repository.count()
