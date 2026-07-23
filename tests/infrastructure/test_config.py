from pathlib import Path

import pytest

from aioffice.infrastructure import AppSettings


def test_app_settings_uses_default_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIOFFICE_DATA_DIR", raising=False)
    monkeypatch.delenv("AIOFFICE_HOST", raising=False)
    monkeypatch.delenv("AIOFFICE_PORT", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_HOST", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_PORT", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_USERNAME", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_MAILBOX", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_USE_SSL", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_POLLING_ENABLED", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY", raising=False)

    settings = AppSettings.from_environment()

    assert settings.data_directory == Path("storage").resolve()
    assert settings.database_path == settings.data_directory / "aioffice.db"
    assert settings.artifacts_directory == settings.data_directory / "artifacts"
    assert settings.incoming_directory == settings.data_directory / "incoming"
    assert settings.processed_directory == settings.data_directory / "processed"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.imap_host is None
    assert settings.imap_port == 993
    assert settings.imap_username is None
    assert settings.imap_password is None
    assert settings.imap_mailbox == "INBOX"
    assert settings.imap_use_ssl is True
    assert settings.imap_polling_enabled is False
    assert settings.imap_polling_interval_seconds == 300
    assert settings.imap_polling_run_immediately is False
    assert settings.imap_max_attachment_bytes == 25 * 1024 * 1024
    assert settings.imap_max_attachments_per_message == 50
    assert settings.document_extraction_max_input_bytes == 50 * 1024 * 1024
    assert settings.document_extraction_max_output_chars == 2_000_000
    assert settings.ai_classification_enabled is False
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_model == "qwen2.5:7b"
    assert settings.ollama_timeout_seconds == 120
    assert settings.ai_classification_max_input_chars == 100_000


def test_app_settings_reads_all_environment_variables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIOFFICE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AIOFFICE_HOST", "0.0.0.0")
    monkeypatch.setenv("AIOFFICE_PORT", "9000")
    monkeypatch.setenv("AIOFFICE_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("AIOFFICE_IMAP_PORT", "1993")
    monkeypatch.setenv("AIOFFICE_IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("AIOFFICE_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("AIOFFICE_IMAP_MAILBOX", "Support")
    monkeypatch.setenv("AIOFFICE_IMAP_USE_SSL", "false")
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_ENABLED", "true")
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS", "600")
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY", "true")

    settings = AppSettings.from_environment()

    assert settings.data_directory == (tmp_path / "data").resolve()
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.imap_host == "imap.example.com"
    assert settings.imap_port == 1993
    assert settings.imap_username == "user@example.com"
    assert settings.imap_password == "secret"
    assert settings.imap_mailbox == "Support"
    assert settings.imap_use_ssl is False
    assert settings.imap_polling_enabled is True
    assert settings.imap_polling_interval_seconds == 600
    assert settings.imap_polling_run_immediately is True
    assert settings.imap_max_attachment_bytes == 25 * 1024 * 1024
    assert settings.imap_max_attachments_per_message == 50
    assert settings.document_extraction_max_input_bytes == 50 * 1024 * 1024
    assert settings.document_extraction_max_output_chars == 2_000_000
    assert settings.ai_classification_enabled is False


def test_app_settings_expands_home_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home_directory = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_directory))
    monkeypatch.setenv("USERPROFILE", str(home_directory))
    monkeypatch.setenv("AIOFFICE_DATA_DIR", "~/aioffice-data")

    settings = AppSettings.from_environment()

    assert settings.data_directory == (home_directory / "aioffice-data").resolve()


def test_app_settings_builds_database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIOFFICE_DATA_DIR", str(tmp_path / "data"))

    settings = AppSettings.from_environment()

    assert settings.database_path == (tmp_path / "data").resolve() / "aioffice.db"


def test_app_settings_builds_artifacts_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIOFFICE_DATA_DIR", str(tmp_path / "data"))

    settings = AppSettings.from_environment()

    assert settings.artifacts_directory == (tmp_path / "data").resolve() / "artifacts"


def test_app_settings_builds_incoming_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIOFFICE_DATA_DIR", str(tmp_path / "data"))

    settings = AppSettings.from_environment()

    assert settings.incoming_directory == (tmp_path / "data").resolve() / "incoming"


def test_app_settings_builds_processed_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIOFFICE_DATA_DIR", str(tmp_path / "data"))

    settings = AppSettings.from_environment()

    assert settings.processed_directory == (tmp_path / "data").resolve() / "processed"


def test_app_settings_converts_port_to_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_PORT", "8010")

    settings = AppSettings.from_environment()

    assert settings.port == 8010


def test_app_settings_rejects_non_numeric_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_PORT", "abc")

    with pytest.raises(ValueError, match="AIOFFICE_PORT must be an integer"):
        AppSettings.from_environment()


def test_app_settings_rejects_zero_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_PORT", "0")

    with pytest.raises(ValueError, match="AIOFFICE_PORT must be between 1 and 65535"):
        AppSettings.from_environment()


def test_app_settings_rejects_port_above_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_PORT", "65536")

    with pytest.raises(ValueError, match="AIOFFICE_PORT must be between 1 and 65535"):
        AppSettings.from_environment()


def test_app_settings_rejects_non_numeric_imap_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_PORT", "abc")

    with pytest.raises(ValueError, match="AIOFFICE_IMAP_PORT must be an integer"):
        AppSettings.from_environment()


def test_app_settings_rejects_invalid_imap_ssl_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_USE_SSL", "maybe")

    with pytest.raises(ValueError, match="AIOFFICE_IMAP_USE_SSL must be 'true' or 'false'"):
        AppSettings.from_environment()


def test_app_settings_parses_false_imap_polling_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_ENABLED", "false")

    settings = AppSettings.from_environment()

    assert settings.imap_polling_enabled is False


def test_app_settings_rejects_invalid_imap_polling_enabled_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_ENABLED", "maybe")

    with pytest.raises(ValueError, match="AIOFFICE_IMAP_POLLING_ENABLED must be 'true' or 'false'"):
        AppSettings.from_environment()


def test_app_settings_allows_minimum_imap_polling_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS", "30")

    settings = AppSettings.from_environment()

    assert settings.imap_polling_interval_seconds == 30


def test_app_settings_allows_maximum_imap_polling_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS", "86400")

    settings = AppSettings.from_environment()

    assert settings.imap_polling_interval_seconds == 86400


def test_app_settings_rejects_imap_polling_interval_below_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS", "29")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS must be between 30 and 86400",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_imap_polling_interval_above_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS", "86401")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS must be between 30 and 86400",
    ):
        AppSettings.from_environment()


def test_app_settings_parses_imap_polling_run_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY", "true")

    settings = AppSettings.from_environment()

    assert settings.imap_polling_run_immediately is True


def test_app_settings_rejects_invalid_imap_polling_run_immediately_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY", "sometimes")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY must be 'true' or 'false'",
    ):
        AppSettings.from_environment()


def test_app_settings_reads_imap_attachment_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES", str(5 * 1024 * 1024))
    monkeypatch.setenv("AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE", "20")

    settings = AppSettings.from_environment()

    assert settings.imap_max_attachment_bytes == 5 * 1024 * 1024
    assert settings.imap_max_attachments_per_message == 20


def test_app_settings_reads_document_extraction_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES", str(10 * 1024 * 1024))
    monkeypatch.setenv("AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS", "123456")

    settings = AppSettings.from_environment()

    assert settings.document_extraction_max_input_bytes == 10 * 1024 * 1024
    assert settings.document_extraction_max_output_chars == 123456


def test_app_settings_rejects_document_extraction_input_below_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES", str(1024 * 1024 - 1))

    with pytest.raises(
        ValueError,
        match="AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES must be between 1048576 and 209715200",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_document_extraction_input_above_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES", str(200 * 1024 * 1024 + 1))

    with pytest.raises(
        ValueError,
        match="AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES must be between 1048576 and 209715200",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_document_extraction_output_below_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS", "9999")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS must be between 10000 and 10000000",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_document_extraction_output_above_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS", "10000001")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS must be between 10000 and 10000000",
    ):
        AppSettings.from_environment()


def test_app_settings_reads_ai_classification_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_AI_CLASSIFICATION_ENABLED", "true")
    monkeypatch.setenv("AIOFFICE_OLLAMA_BASE_URL", "http://ollama.local:11434/")
    monkeypatch.setenv("AIOFFICE_OLLAMA_MODEL", "qwen2.5:14b")
    monkeypatch.setenv("AIOFFICE_OLLAMA_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS", "200000")

    settings = AppSettings.from_environment()

    assert settings.ai_classification_enabled is True
    assert settings.ollama_base_url == "http://ollama.local:11434"
    assert settings.ollama_model == "qwen2.5:14b"
    assert settings.ollama_timeout_seconds == 180
    assert settings.ai_classification_max_input_chars == 200000


def test_app_settings_defaults_reply_draft_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIOFFICE_AI_REPLY_DRAFT_ENABLED", raising=False)
    monkeypatch.delenv("AIOFFICE_REPLY_DRAFT_MODEL", raising=False)
    monkeypatch.delenv("AIOFFICE_REPLY_DRAFT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AIOFFICE_REPLY_DRAFT_MAX_INPUT_CHARS", raising=False)
    monkeypatch.delenv("AIOFFICE_REPLY_DRAFT_MAX_OPERATOR_INSTRUCTION_CHARS", raising=False)

    settings = AppSettings.from_environment()

    assert settings.ai_reply_draft_enabled is False
    assert settings.reply_draft_model == settings.ollama_model
    assert settings.reply_draft_timeout_seconds == 180
    assert settings.reply_draft_max_input_chars == 150_000
    assert settings.reply_draft_max_operator_instruction_chars == 2000


def test_app_settings_reads_reply_draft_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_AI_REPLY_DRAFT_ENABLED", "true")
    monkeypatch.setenv("AIOFFICE_REPLY_DRAFT_MODEL", "qwen3:4b")
    monkeypatch.setenv("AIOFFICE_REPLY_DRAFT_TIMEOUT_SECONDS", "240")
    monkeypatch.setenv("AIOFFICE_REPLY_DRAFT_MAX_INPUT_CHARS", "200000")
    monkeypatch.setenv("AIOFFICE_REPLY_DRAFT_MAX_OPERATOR_INSTRUCTION_CHARS", "3000")

    settings = AppSettings.from_environment()

    assert settings.ai_reply_draft_enabled is True
    assert settings.reply_draft_model == "qwen3:4b"
    assert settings.reply_draft_timeout_seconds == 240
    assert settings.reply_draft_max_input_chars == 200000
    assert settings.reply_draft_max_operator_instruction_chars == 3000


def test_app_settings_falls_back_to_ollama_model_for_blank_reply_draft_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_AI_REPLY_DRAFT_ENABLED", "true")
    monkeypatch.setenv("AIOFFICE_OLLAMA_MODEL", "qwen2.5:14b")
    monkeypatch.setenv("AIOFFICE_REPLY_DRAFT_MODEL", "   ")

    settings = AppSettings.from_environment()

    assert settings.reply_draft_model == "qwen2.5:14b"


def test_app_settings_rejects_invalid_reply_draft_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_AI_REPLY_DRAFT_ENABLED", "maybe")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_AI_REPLY_DRAFT_ENABLED must be 'true' or 'false'",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_reply_draft_timeout_below_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_REPLY_DRAFT_TIMEOUT_SECONDS", "4")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_REPLY_DRAFT_TIMEOUT_SECONDS must be between 5 and 600",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_reply_draft_input_limit_above_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_REPLY_DRAFT_MAX_INPUT_CHARS", "1000001")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_REPLY_DRAFT_MAX_INPUT_CHARS must be between 10000 and 1000000",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_reply_draft_instruction_limit_below_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_REPLY_DRAFT_MAX_OPERATOR_INSTRUCTION_CHARS", "99")

    with pytest.raises(
        ValueError,
        match=(
            "AIOFFICE_REPLY_DRAFT_MAX_OPERATOR_INSTRUCTION_CHARS must be between 100 and 10000"
        ),
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_invalid_ai_classification_boolean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_AI_CLASSIFICATION_ENABLED", "maybe")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_AI_CLASSIFICATION_ENABLED must be 'true' or 'false'",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_invalid_ollama_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_OLLAMA_BASE_URL", "ftp://example.com")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_OLLAMA_BASE_URL must start with 'http://' or 'https://'",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_empty_ollama_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_OLLAMA_MODEL", "   ")

    with pytest.raises(ValueError, match="AIOFFICE_OLLAMA_MODEL must not be empty"):
        AppSettings.from_environment()


def test_app_settings_rejects_ollama_timeout_below_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_OLLAMA_TIMEOUT_SECONDS", "4")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_OLLAMA_TIMEOUT_SECONDS must be between 5 and 600",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_ollama_timeout_above_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOFFICE_OLLAMA_TIMEOUT_SECONDS", "601")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_OLLAMA_TIMEOUT_SECONDS must be between 5 and 600",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_ai_classification_input_below_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS", "9999")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS must be between 10000 and 1000000",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_ai_classification_input_above_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS", "1000001")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS must be between 10000 and 1000000",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_imap_attachment_size_below_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES", str(1024 * 1024 - 1))

    with pytest.raises(
        ValueError,
        match="AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES must be between 1048576 and 104857600",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_imap_attachment_size_above_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES", str(100 * 1024 * 1024 + 1))

    with pytest.raises(
        ValueError,
        match="AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES must be between 1048576 and 104857600",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_imap_attachment_count_below_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE", "0")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE must be between 1 and 200",
    ):
        AppSettings.from_environment()


def test_app_settings_rejects_imap_attachment_count_above_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE", "201")

    with pytest.raises(
        ValueError,
        match="AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE must be between 1 and 200",
    ):
        AppSettings.from_environment()
