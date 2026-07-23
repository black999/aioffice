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
