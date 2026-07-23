from datetime import UTC, datetime

import pytest

from aioffice.application import (
    CaseCategory,
    CaseClassification,
    PersistedCaseClassification,
    format_case_category_label,
    format_confidence_percent,
)
from aioffice.domain import Identifier


def test_all_case_categories_are_supported() -> None:
    assert tuple(category.value for category in CaseCategory) == (
        "general",
        "invoice",
        "complaint",
        "request",
        "contract",
        "official_letter",
        "technical_support",
        "other",
    )


def test_unknown_category_is_rejected() -> None:
    with pytest.raises(ValueError):
        CaseCategory("unknown")


@pytest.mark.parametrize("confidence", (0, 1))
def test_classification_allows_boundary_confidence_values(confidence: int) -> None:
    classification = CaseClassification(
        category=CaseCategory.GENERAL,
        confidence=confidence,
        rationale="Valid rationale",
        model_name="qwen2.5:7b",
    )

    assert classification.confidence == float(confidence)


@pytest.mark.parametrize("confidence", (-0.1, 1.1))
def test_classification_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence must be a number between 0 and 1"):
        CaseClassification(
            category=CaseCategory.GENERAL,
            confidence=confidence,
            rationale="Valid rationale",
            model_name="qwen2.5:7b",
        )


def test_classification_rejects_empty_rationale() -> None:
    with pytest.raises(ValueError, match="rationale must be a non-empty string"):
        CaseClassification(
            category=CaseCategory.GENERAL,
            confidence=0.5,
            rationale="   ",
            model_name="qwen2.5:7b",
        )


def test_classification_truncates_rationale_to_limit() -> None:
    classification = CaseClassification(
        category=CaseCategory.GENERAL,
        confidence=0.5,
        rationale="x" * 800,
        model_name="qwen2.5:7b",
    )

    assert len(classification.rationale) == 500


def test_persisted_classification_validates_timestamp() -> None:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    classification = PersistedCaseClassification(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        category=CaseCategory.INVOICE,
        confidence=0.92,
        rationale="Invoice-related content",
        model_name="qwen2.5:7b",
        classified_at=timestamp,
    )

    assert classification.classified_at == timestamp


def test_format_helpers_return_polish_labels_and_percentages() -> None:
    assert format_case_category_label(CaseCategory.TECHNICAL_SUPPORT) == "Pomoc techniczna"
    assert format_confidence_percent(0.9234) == "92%"
