from dataclasses import dataclass

from aioffice.application import (
    ArtifactRecord,
    CaseCategory,
    CaseClassificationRepository,
    CaseRepository,
    DownloadableArtifact,
    PersistedCase,
    PersistedCaseClassification,
)
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


@dataclass(slots=True)
class _FakeClassificationRepository(CaseClassificationRepository):
    classifications: dict[Identifier, PersistedCaseClassification]
    get_many_calls: int = 0

    def save(self, classification: PersistedCaseClassification) -> None:
        self.classifications[classification.case_id] = classification

    def get(self, case_id: Identifier) -> PersistedCaseClassification | None:
        return self.classifications.get(case_id)

    def get_many(self, case_ids: tuple[Identifier, ...]) -> dict[Identifier, PersistedCaseClassification]:
        self.get_many_calls += 1
        return {
            case_id: classification
            for case_id, classification in self.classifications.items()
            if case_id in case_ids
        }

    def delete(self, case_id: Identifier) -> None:
        self.classifications.pop(case_id, None)


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
    assert cases[0].category_label is None
    assert cases[1].case_id == str(second_case.id)
    assert cases[1].case_reference == "CASE-000002"


def test_case_dashboard_service_uses_batch_classification_lookup() -> None:
    first_case = Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    second_case = Case(id=Identifier.from_string("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    classifications = _FakeClassificationRepository(
        classifications={
            first_case.id: PersistedCaseClassification(
                case_id=first_case.id,
                category=CaseCategory.INVOICE,
                confidence=0.92,
                rationale="Invoice-related content",
                model_name="qwen2.5:7b",
                classified_at="2026-07-23T12:00:00+00:00",
            )
        }
    )
    service = CaseDashboardService(
        repository=_FakeCaseRepository(
            cases=(
                PersistedCase(case=first_case, reference_number=1, status="open", created_at="2026-07-22T12:00:00+00:00"),
                PersistedCase(case=second_case, reference_number=2, status="open", created_at="2026-07-22T12:01:00+00:00"),
            )
        ),
        classification_repository=classifications,
    )

    cases = service.list_cases()

    assert classifications.get_many_calls == 1
    assert cases[0].category_label == "Faktura / rozliczenie"
    assert cases[1].category_label is None
