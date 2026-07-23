"""Reply draft models and contracts for the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from aioffice.application.classification import CaseCategory
from aioffice.domain import Identifier


MAX_REPLY_DRAFT_SUBJECT_CHARS = 200
MAX_REPLY_DRAFT_BODY_CHARS = 20_000
MAX_APPROVER_NAME_CHARS = 200


class ReplyDraftGenerationError(RuntimeError):
    """Raised when reply draft generation cannot be completed."""


class ReplyDraftResponseError(ReplyDraftGenerationError):
    """Raised when the model response is structurally invalid."""


class ReplyDraftStatus(StrEnum):
    """Current lifecycle state of a persisted reply draft."""

    GENERATED = "generated"
    EDITED = "edited"
    APPROVED = "approved"


def _normalize_text(value: object, *, field_name: str, max_chars: int, trim: bool) -> str:
    if not isinstance(value, str):
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    normalized = value.replace("\x00", "").strip()
    if trim:
        normalized = normalized[:max_chars].strip()
    if not normalized:
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    if len(normalized) > max_chars:
        msg = f"{field_name} must be at most {max_chars} characters long"
        raise ValueError(msg)
    return normalized


def normalize_operator_instruction(value: str | None, *, max_chars: int) -> str | None:
    """Normalize an optional operator instruction."""

    if value is None:
        return None
    normalized = value.replace("\x00", "").strip()
    if not normalized:
        return None
    if len(normalized) > max_chars:
        msg = f"operator_instruction must be at most {max_chars} characters long"
        raise ValueError(msg)
    return normalized


def normalize_approver_name(value: str) -> str:
    """Normalize a manually entered approver name."""

    return _normalize_text(
        value,
        field_name="approved_by",
        max_chars=MAX_APPROVER_NAME_CHARS,
        trim=False,
    )


def validate_reply_draft_timestamp(value: str) -> str:
    """Validate a persisted reply draft timestamp."""

    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        msg = "reply draft timestamp must be a valid ISO-8601 datetime string"
        raise ValueError(msg) from error
    return value


@dataclass(frozen=True, slots=True)
class GeneratedReplyDraft:
    """Validated reply draft produced by a local AI model."""

    subject: str
    body: str
    model_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject",
            _normalize_text(
                self.subject,
                field_name="subject",
                max_chars=MAX_REPLY_DRAFT_SUBJECT_CHARS,
                trim=True,
            ),
        )
        object.__setattr__(
            self,
            "body",
            _normalize_text(
                self.body,
                field_name="body",
                max_chars=MAX_REPLY_DRAFT_BODY_CHARS,
                trim=True,
            ),
        )
        if not self.model_name.strip():
            msg = "model_name must not be empty"
            raise ValueError(msg)
        object.__setattr__(self, "model_name", self.model_name.strip())


@dataclass(frozen=True, slots=True)
class PersistedReplyDraft:
    """Reply draft stored for a case."""

    case_id: Identifier
    subject: str
    body: str
    status: ReplyDraftStatus
    model_name: str
    operator_instruction: str | None
    approved_by: str | None
    approved_at: str | None
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject",
            _normalize_text(
                self.subject,
                field_name="subject",
                max_chars=MAX_REPLY_DRAFT_SUBJECT_CHARS,
                trim=False,
            ),
        )
        object.__setattr__(
            self,
            "body",
            _normalize_text(
                self.body,
                field_name="body",
                max_chars=MAX_REPLY_DRAFT_BODY_CHARS,
                trim=False,
            ),
        )
        if not self.model_name.strip():
            msg = "model_name must not be empty"
            raise ValueError(msg)
        object.__setattr__(self, "model_name", self.model_name.strip())
        object.__setattr__(
            self,
            "operator_instruction",
            None if self.operator_instruction is None else self.operator_instruction.replace("\x00", "").strip() or None,
        )
        object.__setattr__(
            self,
            "approved_by",
            None if self.approved_by is None else normalize_approver_name(self.approved_by),
        )
        object.__setattr__(
            self,
            "approved_at",
            None if self.approved_at is None else validate_reply_draft_timestamp(self.approved_at),
        )
        object.__setattr__(self, "created_at", validate_reply_draft_timestamp(self.created_at))
        object.__setattr__(self, "updated_at", validate_reply_draft_timestamp(self.updated_at))
        self._validate_approval_consistency()

    def _validate_approval_consistency(self) -> None:
        if self.status is ReplyDraftStatus.APPROVED:
            if self.approved_by is None:
                msg = "approved drafts must define approved_by"
                raise ValueError(msg)
            if self.approved_at is None:
                msg = "approved drafts must define approved_at"
                raise ValueError(msg)
            return

        if self.approved_by is not None or self.approved_at is not None:
            msg = "non-approved drafts must not define approval metadata"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ReplyDraftGenerationResult:
    """Outcome of a manual reply draft generation request."""

    draft: PersistedReplyDraft | None
    skipped: bool
    reason: str | None


class ReplyDraftGenerator(Protocol):
    """Application-facing contract for manual AI reply draft generation."""

    def generate(
        self,
        *,
        case_text: str,
        category: CaseCategory | None,
        operator_instruction: str | None,
    ) -> GeneratedReplyDraft:
        """Generate a reply draft for the given case context."""


class ReplyDraftRepository(Protocol):
    """Persistence contract for the latest reply draft per case."""

    def save(self, draft: PersistedReplyDraft) -> None:
        """Persist or replace a reply draft."""

    def get(self, case_id: Identifier) -> PersistedReplyDraft | None:
        """Load a reply draft if it exists."""

    def get_statuses(
        self,
        case_ids: tuple[Identifier, ...],
    ) -> dict[Identifier, ReplyDraftStatus]:
        """Load reply draft statuses for many cases in one call."""

    def delete(self, case_id: Identifier) -> None:
        """Delete the current reply draft for a case."""


def build_persisted_reply_draft(
    *,
    case_id: Identifier,
    generated_draft: GeneratedReplyDraft,
    operator_instruction: str | None,
    existing_draft: PersistedReplyDraft | None = None,
    status: ReplyDraftStatus = ReplyDraftStatus.GENERATED,
    approved_by: str | None = None,
    approved_at: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> PersistedReplyDraft:
    """Create a validated persisted reply draft with UTC timestamps."""

    timestamp = updated_at or datetime.now(UTC).isoformat(timespec="seconds")
    return PersistedReplyDraft(
        case_id=case_id,
        subject=generated_draft.subject,
        body=generated_draft.body,
        status=status,
        model_name=generated_draft.model_name,
        operator_instruction=operator_instruction,
        approved_by=approved_by,
        approved_at=approved_at,
        created_at=created_at or (existing_draft.created_at if existing_draft is not None else timestamp),
        updated_at=timestamp,
    )


def validate_manual_reply_draft_subject(subject: str) -> str:
    """Validate a manually edited reply draft subject."""

    return _normalize_text(
        subject,
        field_name="subject",
        max_chars=MAX_REPLY_DRAFT_SUBJECT_CHARS,
        trim=False,
    )


def validate_manual_reply_draft_body(body: str) -> str:
    """Validate a manually edited reply draft body."""

    return _normalize_text(
        body,
        field_name="body",
        max_chars=MAX_REPLY_DRAFT_BODY_CHARS,
        trim=False,
    )


def format_reply_draft_status_label(status: ReplyDraftStatus) -> str:
    """Return a user-facing Polish label for a reply draft status."""

    return {
        ReplyDraftStatus.GENERATED: "Wygenerowany",
        ReplyDraftStatus.EDITED: "Edytowany",
        ReplyDraftStatus.APPROVED: "Zatwierdzony",
    }[status]
