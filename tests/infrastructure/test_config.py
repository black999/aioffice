from pathlib import Path

import pytest

from aioffice.infrastructure import AppSettings


def test_app_settings_uses_default_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIOFFICE_DATA_DIR", raising=False)
    monkeypatch.delenv("AIOFFICE_HOST", raising=False)
    monkeypatch.delenv("AIOFFICE_PORT", raising=False)

    settings = AppSettings.from_environment()

    assert settings.data_directory == Path("storage").resolve()
    assert settings.database_path == settings.data_directory / "aioffice.db"
    assert settings.artifacts_directory == settings.data_directory / "artifacts"
    assert settings.incoming_directory == settings.data_directory / "incoming"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_app_settings_reads_all_environment_variables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIOFFICE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AIOFFICE_HOST", "0.0.0.0")
    monkeypatch.setenv("AIOFFICE_PORT", "9000")

    settings = AppSettings.from_environment()

    assert settings.data_directory == (tmp_path / "data").resolve()
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000


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
