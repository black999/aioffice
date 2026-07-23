"""Case classification models and contracts for the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from aioffice.domain import Identifier


MAX_CLASSIFICATION_RATIONALE_CHARS = 500


class CaseClassificationError(RuntimeError):
    """Raised when case classification cannot be completed."""


class CaseClassificationResponseError(CaseClassificationError):
    """Raised when the model response is structurally invalid."""


class CaseCategory(StrEnum):
    """Stable technical categories used for case classification."""

    GENERAL = "general"
    INVOICE = "invoice"
    COMPLAINT = "complaint"
    REQUEST = "request"
    CONTRACT = "contract"
    OFFICIAL_LETTER = "official_letter"
    TECHNICAL_SUPPORT = "technical_support"
    OTHER = "other"


def _normalize_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = "confidence must be a number between 0 and 1"
        raise ValueError(msg)
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        msg = "confidence must be a number between 0 and 1"
        raise ValueError(msg)
    return normalized


def normalize_rationale(value: object) -> str:
    """Normalize a classification rationale to the supported persisted form."""

    if not isinstance(value, str):
        msg = "rationale must be a non-empty string"
        raise ValueError(msg)
    normalized = value.strip()
    if not normalized:
        msg = "rationale must be a non-empty string"
        raise ValueError(msg)
    return normalized[:MAX_CLASSIFICATION_RATIONALE_CHARS]


def validate_classification_timestamp(value: str) -> str:
    """Validate a persisted classification timestamp."""

    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        msg = "classified_at must be a valid ISO-8601 datetime string"
        raise ValueError(msg) from error
    return value


@dataclass(frozen=True, slots=True)
class CaseClassification:
    """Validated classification produced by a local AI model."""

    category: CaseCategory
    confidence: float
    rationale: str
    model_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        object.__setattr__(self, "rationale", normalize_rationale(self.rationale))
        if not self.model_name.strip():
            msg = "model_name must not be empty"
            raise ValueError(msg)
        object.__setattr__(self, "model_name", self.model_name.strip())


@dataclass(frozen=True, slots=True)
class PersistedCaseClassification:
    """Classification stored for a case."""

    case_id: Identifier
    category: CaseCategory
    confidence: float
    rationale: str
    model_name: str
    classified_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        object.__setattr__(self, "rationale", normalize_rationale(self.rationale))
        if not self.model_name.strip():
            msg = "model_name must not be empty"
            raise ValueError(msg)
        object.__setattr__(self, "model_name", self.model_name.strip())
        object.__setattr__(self, "classified_at", validate_classification_timestamp(self.classified_at))


@dataclass(frozen=True, slots=True)
class CaseClassificationResult:
    """Outcome of a manual case classification request."""

    classification: PersistedCaseClassification | None
    skipped: bool
    reason: str | None


class CaseClassifier(Protocol):
    """Application-facing contract for manual case classification."""

    def classify(self, text: str) -> CaseClassification:
        """Classify the given textual case content."""


class CaseClassificationRepository(Protocol):
    """Persistence contract for the latest case classification."""

    def save(self, classification: PersistedCaseClassification) -> None:
        """Persist or replace a case classification."""

    def get(self, case_id: Identifier) -> PersistedCaseClassification | None:
        """Load a case classification if it exists."""

    def get_many(
        self,
        case_ids: tuple[Identifier, ...],
    ) -> dict[Identifier, PersistedCaseClassification]:
        """Load classifications for many cases in one call."""

    def delete(self, case_id: Identifier) -> None:
        """Delete the current classification for a case."""


def build_persisted_case_classification(
    *,
    case_id: Identifier,
    classification: CaseClassification,
    classified_at: str | None = None,
) -> PersistedCaseClassification:
    """Create a validated persisted classification with a UTC timestamp."""

    timestamp = classified_at or datetime.now(UTC).isoformat(timespec="seconds")
    return PersistedCaseClassification(
        case_id=case_id,
        category=classification.category,
        confidence=classification.confidence,
        rationale=classification.rationale,
        model_name=classification.model_name,
        classified_at=timestamp,
    )


def format_case_category_label(category: CaseCategory) -> str:
    """Return a user-facing Polish label for a stable technical category."""

    return {
        CaseCategory.GENERAL: "Ogólne",
        CaseCategory.INVOICE: "Faktura / rozliczenie",
        CaseCategory.COMPLAINT: "Reklamacja / skarga",
        CaseCategory.REQUEST: "Wniosek / prośba",
        CaseCategory.CONTRACT: "Umowa",
        CaseCategory.OFFICIAL_LETTER: "Pismo urzędowe",
        CaseCategory.TECHNICAL_SUPPORT: "Pomoc techniczna",
        CaseCategory.OTHER: "Inne",
    }[category]


def format_confidence_percent(confidence: float) -> str:
    """Format a confidence score as a coarse percentage for the UI."""

    normalized = _normalize_confidence(confidence)
    return f"{round(normalized * 100):.0f}%"
