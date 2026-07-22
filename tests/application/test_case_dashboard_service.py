from dataclasses import dataclass

from aioffice.application import CaseRepository, PersistedCase
from aioffice.application.services import CaseDashboardService
from aioffice.domain import Case, Identifier


@dataclass(slots=True)
class _FakeCaseRepository(CaseRepository):
    cases: tuple[PersistedCase, ...]

    def save(self, case: Case, reference_number: int) -> None:
        msg = "save is not used in this test"
        raise NotImplementedError(msg)

    def get(self, case_id: Identifier) -> PersistedCase | None:
        return next((case for case in self.cases if case.case.id == case_id), None)

    def list(self) -> tuple[PersistedCase, ...]:
        return self.cases

    def count(self) -> int:
        return len(self.cases)


def test_case_dashboard_service_returns_case_count_and_summaries() -> None:
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    repository = _FakeCaseRepository(
        cases=(
            PersistedCase(case=first_case, reference_number=1, status="open", created_at="2026-07-22T12:00:00+00:00"),
            PersistedCase(case=second_case, reference_number=2, status="open", created_at="2026-07-22T12:01:00+00:00"),
        )
    )
    service = CaseDashboardService(repository=repository)

    cases = service.list_cases()

    assert service.count_cases() == 2
    assert cases[0].case_reference == "CASE-000001"
    assert cases[0].status == "open"
    assert cases[1].case_reference == "CASE-000002"
