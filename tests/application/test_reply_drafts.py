import pytest

from aioffice.application import (
    GeneratedReplyDraft,
    PersistedReplyDraft,
    ReplyDraftStatus,
    format_reply_draft_status_label,
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
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:01:00+00:00",
    )

    assert draft.body == "Ala ma kota"
    assert draft.operator_instruction == "Uprzejmie"


def test_persisted_reply_draft_rejects_invalid_timestamp() -> None:
    case_id = Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    with pytest.raises(ValueError, match="valid ISO-8601"):
        PersistedReplyDraft(
            case_id=case_id,
            subject="Temat",
            body="Tresc",
            status=ReplyDraftStatus.GENERATED,
            model_name="qwen3:4b",
            operator_instruction=None,
            created_at="invalid",
            updated_at="2026-07-23T10:01:00+00:00",
        )


def test_normalize_operator_instruction_returns_none_for_blank_value() -> None:
    assert normalize_operator_instruction("   ", max_chars=2000) is None


def test_normalize_operator_instruction_rejects_value_over_limit() -> None:
    with pytest.raises(ValueError, match="operator_instruction must be at most 5 characters long"):
        normalize_operator_instruction("123456", max_chars=5)


def test_manual_edit_validators_reject_values_over_limit() -> None:
    with pytest.raises(ValueError, match="subject must be at most 200 characters long"):
        validate_manual_reply_draft_subject("x" * 201)
    with pytest.raises(ValueError, match="body must be at most 20000 characters long"):
        validate_manual_reply_draft_body("x" * 20_001)


def test_reply_draft_status_labels_are_polish() -> None:
    assert format_reply_draft_status_label(ReplyDraftStatus.GENERATED) == "Wygenerowany"
    assert format_reply_draft_status_label(ReplyDraftStatus.EDITED) == "Edytowany"
