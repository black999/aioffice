from __future__ import annotations

import time
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aioffice.application.services import DocumentImportService
from aioffice.domain import Case
from aioffice.infrastructure import AppSettings
from aioffice.infrastructure.web.app import create_app


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        host="127.0.0.1",
        port=8000,
    )


def wait_until(predicate: Callable[[], bool], timeout: float = 2.0, interval: float = 0.05) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    msg = "Condition was not met before timeout"
    raise AssertionError(msg)


def test_lifespan_creates_incoming_directory_and_supports_import(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert settings.incoming_directory.exists()
        source_path = settings.incoming_directory / "offer.pdf"
        source_path.write_bytes(b"offer")

        def dashboard_has_case() -> bool:
            return "CASE-000001" in client.get("/").text

        wait_until(dashboard_has_case)

        dashboard = client.get("/")
        match = re.search(r'/cases/([0-9a-f-]{36})', dashboard.text)
        assert match is not None
        workspace = client.get(f"/cases/{match.group(1)}")

        assert dashboard.status_code == 200
        assert "CASE-000001" in dashboard.text
        assert settings.artifacts_directory.exists()
        artifact_files = list(settings.artifacts_directory.rglob("*.pdf"))
        assert len(artifact_files) == 1
        assert workspace.status_code == 200
        assert "artifacts/" in workspace.text
        assert str(settings.data_directory) not in workspace.text


def test_non_pdf_is_ignored_by_runtime(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        source_path = settings.incoming_directory / "offer.txt"
        source_path.write_bytes(b"offer")
        time.sleep(0.2)

        response = client.get("/")

        assert "CASE-000001" not in response.text


def test_import_error_does_not_stop_watch_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    original_import_pdf = DocumentImportService.import_pdf

    def import_pdf(self: DocumentImportService, source_path: Path) -> Case | None:
        if source_path.name == "broken.pdf":
            raise RuntimeError("boom")
        return original_import_pdf(self, source_path)

    monkeypatch.setattr(DocumentImportService, "import_pdf", import_pdf)

    with TestClient(create_app(settings)) as client:
        broken_path = settings.incoming_directory / "broken.pdf"
        broken_path.write_bytes(b"broken")
        good_path = settings.incoming_directory / "good.pdf"
        good_path.write_bytes(b"good")

        def dashboard_has_case() -> bool:
            return "CASE-000001" in client.get("/").text

        wait_until(dashboard_has_case)

        response = client.get("/")

        assert response.status_code == 200
        assert "CASE-000001" in response.text
        assert broken_path.exists()


def test_lifespan_calls_watch_folder_start_and_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    calls: list[str] = []

    from aioffice.infrastructure.watch_folder import WatchFolder

    original_start = WatchFolder.start
    original_stop = WatchFolder.stop

    def start(self: WatchFolder) -> None:
        calls.append("start")
        original_start(self)

    def stop(self: WatchFolder) -> None:
        calls.append("stop")
        original_stop(self)

    monkeypatch.setattr(WatchFolder, "start", start)
    monkeypatch.setattr(WatchFolder, "stop", stop)

    with TestClient(create_app(settings)):
        pass

    assert calls == ["start", "stop"]


def test_lifespan_closes_sqlite_resources_on_shutdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    closed: list[str] = []

    from aioffice.infrastructure.sqlite_repository import SQLiteCaseNumberProvider, SQLiteCaseRepository

    original_repo_close = SQLiteCaseRepository.close
    original_provider_close = SQLiteCaseNumberProvider.close

    def repo_close(self: SQLiteCaseRepository) -> None:
        closed.append("repository")
        original_repo_close(self)

    def provider_close(self: SQLiteCaseNumberProvider) -> None:
        closed.append("number_provider")
        original_provider_close(self)

    monkeypatch.setattr(SQLiteCaseRepository, "close", repo_close)
    monkeypatch.setattr(SQLiteCaseNumberProvider, "close", provider_close)

    with TestClient(create_app(settings)):
        pass

    assert closed.count("repository") == 2
    assert closed.count("number_provider") == 1


def test_lifespan_closes_resources_when_watch_folder_start_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    calls: list[str] = []

    from aioffice.infrastructure.sqlite_repository import SQLiteCaseNumberProvider, SQLiteCaseRepository
    from aioffice.infrastructure.watch_folder import WatchFolder

    def start(self: WatchFolder) -> None:
        calls.append("start")
        raise RuntimeError("watch start failed")

    def stop(self: WatchFolder) -> None:
        calls.append("stop")

    original_repo_close = SQLiteCaseRepository.close
    original_provider_close = SQLiteCaseNumberProvider.close

    def repo_close(self: SQLiteCaseRepository) -> None:
        calls.append("repository")
        original_repo_close(self)

    def provider_close(self: SQLiteCaseNumberProvider) -> None:
        calls.append("number_provider")
        original_provider_close(self)

    monkeypatch.setattr(WatchFolder, "start", start)
    monkeypatch.setattr(WatchFolder, "stop", stop)
    monkeypatch.setattr(SQLiteCaseRepository, "close", repo_close)
    monkeypatch.setattr(SQLiteCaseNumberProvider, "close", provider_close)

    with pytest.raises(RuntimeError, match="watch start failed"):
        with TestClient(create_app(settings)):
            pass

    assert calls.count("start") == 1
    assert calls.count("stop") == 1
    assert calls.count("repository") == 2
    assert calls.count("number_provider") == 1
