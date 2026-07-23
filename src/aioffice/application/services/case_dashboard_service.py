"""Read-only application service for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from aioffice.application import (
    CaseClassificationRepository,
    CaseRepository,
    ReplyDraftRepository,
    format_case_category_label,
    format_reply_draft_status_label,
)
from aioffice.application.case_numbers import format_case_reference


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """Minimal read model for displaying a case."""

    case_id: str
    case_reference: str
    status: str
    category_label: str | None
    reply_draft_status_label: str | None


@dataclass(slots=True)
class CaseDashboardService:
    """Provide read-only case data for the web interface."""

    repository: CaseRepository
    classification_repository: CaseClassificationRepository | None = None
    reply_draft_repository: ReplyDraftRepository | None = None

    def list_cases(self) -> tuple[CaseSummary, ...]:
        """Return cases formatted for dashboard rendering."""

        persisted_cases = self.repository.list()
        classifications = {}
        reply_draft_statuses = {}
        if self.classification_repository is not None:
            classifications = self.classification_repository.get_many(
                tuple(persisted_case.case.id for persisted_case in persisted_cases)
            )
        if self.reply_draft_repository is not None:
            reply_draft_statuses = self.reply_draft_repository.get_statuses(
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
                reply_draft_status_label=(
                    format_reply_draft_status_label(reply_draft_statuses[persisted_case.case.id])
                    if persisted_case.case.id in reply_draft_statuses
                    else None
                ),
            )
            for persisted_case in persisted_cases
        )

    def count_cases(self) -> int:
        """Return the total number of persisted cases."""

        return self.repository.count()
