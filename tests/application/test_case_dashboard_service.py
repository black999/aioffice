from dataclasses import dataclass

from aioffice.application import CaseRepository
from aioffice.application.services import CaseDashboardService
from aioffice.domain import Case, Identifier


@dataclass(slots=True)
class _FakeCaseRepository(CaseRepository):
    cases: tuple[Case, ...]

    def save(self, case: Case) -> None:
        msg = "save is not used in this test"
        raise NotImplementedError(msg)

    def get(self, case_id: Identifier) -> Case | None:
        return next((case for case in self.cases if case.id == case_id), None)

    def list(self) -> tuple[Case, ...]:
        return self.cases

    def count(self) -> int:
        return len(self.cases)


def test_case_dashboard_service_returns_case_count_and_summaries() -> None:
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    repository = _FakeCaseRepository(cases=(first_case, second_case))
    service = CaseDashboardService(repository=repository)

    cases = service.list_cases()

    assert service.count_cases() == 2
    assert cases[0].case_id == str(first_case.id)
    assert cases[0].status == "open"
    assert cases[1].case_id == str(second_case.id)
