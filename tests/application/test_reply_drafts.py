import pytest

from aioffice.application import (
    GeneratedReplyDraft,
    MAX_APPROVER_NAME_CHARS,
    PersistedReplyDraft,
    ReplyDraftStatus,
    format_reply_draft_status_label,
    normalize_approver_name,
    normalize_operator_instruction,
    validate_manual_reply_draft_body,
    validate_manual_reply_draft_subject,
)
from aioffice.domain import Identifier


def test_generated_reply_draft_trims_values_and_validates_model_name() -> None:
    draft = GeneratedReplyDraft(
        subject="  Temat  ",
        body="  Tresc  ",
        model_name=" qwen3:4b ",
    )

    assert draft.subject == "Temat"
    assert draft.body == "Tresc"
    assert draft.model_name == "qwen3:4b"


def test_generated_reply_draft_rejects_empty_subject() -> None:
    with pytest.raises(ValueError, match="subject must be a non-empty string"):
        GeneratedReplyDraft(subject="   ", body="Tresc", model_name="qwen3:4b")


def test_generated_reply_draft_trims_subject_and_body_to_limits() -> None:
    draft = GeneratedReplyDraft(
        subject="x" * 250,
        body="y" * 25_000,
        model_name="qwen3:4b",
    )

    assert len(draft.subject) == 200
    assert len(draft.body) == 20_000


def test_persisted_reply_draft_validates_timestamps_and_removes_nul_from_body() -> None:
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    draft = PersistedReplyDraft(
        case_id=case_id,
        subject="Temat",
        body="Ala\x00 ma kota",
        status=ReplyDraftStatus.GENERATED,
        model_name="qwen3:4b",
        operator_instruction="  Uprzejmie  ",
        approved_by=None,
        approved_at=None,
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:01:00+00:00",
    )

    assert draft.body == "Ala ma kota"
    assert draft.operator_instruction == "Uprzejmie"


def test_persisted_reply_draft_accepts_consistent_approved_state() -> None:
    draft = PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject="Temat",
        body="Tresc",
        status=ReplyDraftStatus.APPROVED,
        model_name="qwen3:4b",
        operator_instruction=None,
        approved_by="Jan Kowalski",
        approved_at="2026-07-23T10:02:00+00:00",
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:02:00+00:00",
    )

    assert draft.approved_by == "Jan Kowalski"
    assert draft.approved_at == "2026-07-23T10:02:00+00:00"


@pytest.mark.parametrize(
    ("status", "approved_by", "approved_at", "match"),
    [
        (ReplyDraftStatus.APPROVED, None, "2026-07-23T10:02:00+00:00", "approved_by"),
        (ReplyDraftStatus.APPROVED, "Jan", None, "approved_at"),
        (ReplyDraftStatus.GENERATED, "Jan", None, "non-approved"),
        (ReplyDraftStatus.EDITED, None, "2026-07-23T10:02:00+00:00", "non-approved"),
    ],
)
def test_persisted_reply_draft_rejects_inconsistent_approval_data(
    status: ReplyDraftStatus,
    approved_by: str | None,
    approved_at: str | None,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        PersistedReplyDraft(
            case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            subject="Temat",
            body="Tresc",
            status=status,
            model_name="qwen3:4b",
            operator_instruction=None,
            approved_by=approved_by,
            approved_at=approved_at,
            created_at="2026-07-23T10:00:00+00:00",
            updated_at="2026-07-23T10:01:00+00:00",
        )


def test_persisted_reply_draft_rejects_invalid_timestamp() -> None:
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    with pytest.raises(ValueError, match="valid ISO-8601"):
        PersistedReplyDraft(
            case_id=case_id,
            subject="Temat",
            body="Tresc",
            status=ReplyDraftStatus.APPROVED,
            model_name="qwen3:4b",
            operator_instruction=None,
            approved_by="Jan Kowalski",
            approved_at="invalid",
            created_at="2026-07-23T10:00:00+00:00",
            updated_at="2026-07-23T10:01:00+00:00",
        )


def test_normalize_operator_instruction_returns_none_for_blank_value() -> None:
    assert normalize_operator_instruction("   ", max_chars=2000) is None


def test_normalize_operator_instruction_rejects_value_over_limit() -> None:
    with pytest.raises(ValueError, match="operator_instruction must be at most 5 characters long"):
        normalize_operator_instruction("123456", max_chars=5)


def test_normalize_approver_name_rejects_blank_value() -> None:
    with pytest.raises(ValueError, match="approved_by must be a non-empty string"):
        normalize_approver_name("   ")


def test_normalize_approver_name_accepts_exact_limit() -> None:
    normalized = normalize_approver_name("x" * MAX_APPROVER_NAME_CHARS)

    assert normalized == "x" * MAX_APPROVER_NAME_CHARS


def test_normalize_approver_name_rejects_value_over_limit() -> None:
    with pytest.raises(
        ValueError,
        match=f"approved_by must be at most {MAX_APPROVER_NAME_CHARS} characters long",
    ):
        normalize_approver_name("x" * (MAX_APPROVER_NAME_CHARS + 1))


def test_normalize_approver_name_removes_nul_characters() -> None:
    assert normalize_approver_name(" Jan\x00 Kowalski ") == "Jan Kowalski"


def test_manual_edit_validators_reject_values_over_limit() -> None:
    with pytest.raises(ValueError, match="subject must be at most 200 characters long"):
        validate_manual_reply_draft_subject("x" * 201)
    with pytest.raises(ValueError, match="body must be at most 20000 characters long"):
        validate_manual_reply_draft_body("x" * 20_001)


def test_reply_draft_status_labels_are_polish() -> None:
    assert format_reply_draft_status_label(ReplyDraftStatus.GENERATED) == "Wygenerowany"
    assert format_reply_draft_status_label(ReplyDraftStatus.EDITED) == "Edytowany"
    assert format_reply_draft_status_label(ReplyDraftStatus.APPROVED) == "Zatwierdzony"
