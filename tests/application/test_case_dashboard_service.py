from dataclasses import dataclass

from aioffice.application import ArtifactRecord, CaseRepository, DownloadableArtifact, PersistedCase
from aioffice.application.services import CaseDashboardService
from aioffice.domain import Case, Identifier


@dataclass(slots=True)
class _FakeCaseRepository(CaseRepository):
    cases: tuple[PersistedCase, ...]

    def save(
        self,
        case: Case,
        reference_number: int,
        artifact_records: tuple[ArtifactRecord, ...] | None = None,
    ) -> None:
        msg = "save is not used in this test"
        raise NotImplementedError(msg)

    def get(self, case_id: Identifier) -> PersistedCase | None:
        return next((case for case in self.cases if case.case.id == case_id), None)

    def get_by_artifact_locator(self, locator: str) -> PersistedCase | None:
        return next(
            (
                persisted_case
                for persisted_case in self.cases
                if persisted_case.case.artifacts
                and persisted_case.case.artifacts[0].storage_reference.locator == locator
            ),
            None,
        )

    def list(self) -> tuple[PersistedCase, ...]:
        return self.cases

    def count(self) -> int:
        return len(self.cases)

    def get_artifact(self, case_id: Identifier, position: int) -> DownloadableArtifact | None:
        return None


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
    assert cases[0].case_id == str(first_case.id)
    assert cases[0].case_reference == "CASE-000001"
    assert cases[0].status == "open"
    assert cases[1].case_id == str(second_case.id)
    assert cases[1].case_reference == "CASE-000002"
