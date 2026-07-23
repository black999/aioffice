"""Read-only application service for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from aioffice.application import CaseClassificationRepository, CaseRepository, format_case_category_label
from aioffice.application.case_numbers import format_case_reference


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """Minimal read model for displaying a case."""

    case_id: str
    case_reference: str
    status: str
    category_label: str | None


@dataclass(slots=True)
class CaseDashboardService:
    """Provide read-only case data for the web interface."""

    repository: CaseRepository
    classification_repository: CaseClassificationRepository | None = None

    def list_cases(self) -> tuple[CaseSummary, ...]:
        """Return cases formatted for dashboard rendering."""

        persisted_cases = self.repository.list()
        classifications = {}
        if self.classification_repository is not None:
            classifications = self.classification_repository.get_many(
                tuple(persisted_case.case.id for persisted_case in persisted_cases)
            )
        return tuple(
            CaseSummary(
                case_id=str(persisted_case.case.id),
                case_reference=format_case_reference(persisted_case.reference_number),
                status=persisted_case.status,
                category_label=(
                    format_case_category_label(classifications[persisted_case.case.id].category)
                    if persisted_case.case.id in classifications
                    else None
                ),
            )
            for persisted_case in persisted_cases
        )

    def count_cases(self) -> int:
        """Return the total number of persisted cases."""

        return self.repository.count()
