from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aioffice.application import MailImportResult
from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference
from aioffice.infrastructure import AppSettings, SQLiteCaseNumberProvider, SQLiteCaseRepository
from aioffice.infrastructure.web.app import create_app


@dataclass(slots=True)
class _FakeMailImportService:
    result: MailImportResult = MailImportResult(imported=0, skipped=0, failed=0)
    exception: Exception | None = None
    on_call: Callable[[], None] | None = None
    calls: int = 0

    def import_new_messages(self) -> MailImportResult:
        self.calls += 1
        if self.on_call is not None:
            self.on_call()
        if self.exception is not None:
            raise self.exception
        return self.result


def _settings(tmp_path: Path, *, with_imap: bool = False) -> AppSettings:
    return AppSettings(
        data_directory=tmp_path / "configured-data",
        database_path=tmp_path / "configured-data" / "aioffice.db",
        artifacts_directory=tmp_path / "configured-data" / "artifacts",
        incoming_directory=tmp_path / "configured-data" / "incoming",
        processed_directory=tmp_path / "configured-data" / "processed",
        host="127.0.0.1",
        port=8000,
        imap_host="imap.example.com" if with_imap else None,
        imap_username="user@example.com" if with_imap else None,
        imap_password="secret" if with_imap else None,
    )


def _save_case(
    database_path: Path,
    *,
    case_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    reference_number: int = 1,
    with_artifact: bool = False,
) -> None:
    repository = SQLiteCaseRepository(database_path=database_path)
    case = Case(id=Identifier.from_string(case_id))
    if with_artifact:
        case.add_artifact(
            Artifact(
                artifact_type=ArtifactType.PDF,
                storage_reference=StorageReference(
                    storage_name="filesystem",
                    locator="artifacts/aa/bb/document.pdf",
                ),
            )
        )
    repository.save(case, reference_number=reference_number)
    repository.close()


def test_get_root_returns_http_200_and_displays_cases(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _save_case(settings.database_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "AI Office" in response.text
    assert "Number of Cases" in response.text
    assert '<a href="/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"><code>CASE-000001</code></a>' in response.text


def test_dashboard_shows_import_button_when_imap_service_exists(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)

    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'form method="post" action="/admin/import-mail"' in response.text
    assert "Importuj poczt" in response.text


def test_dashboard_hides_import_button_without_imap_configuration(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'action="/admin/import-mail"' not in response.text
    assert "Import IMAP nie jest skonfigurowany." in response.text


def test_dashboard_displays_mail_import_success_message(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/?mail_imported=3&mail_skipped=12&mail_failed=1")

    assert response.status_code == 200
    assert "Import poczty zako" in response.text
    assert "Zaimportowano: 3, pomini" in response.text
    assert "b" in response.text


def test_dashboard_displays_mail_import_error_message(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/?mail_import_error=1")

    assert response.status_code == 200
    assert "Nie uda" in response.text


def test_dashboard_displays_mail_import_busy_message(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/?mail_import_busy=1")

    assert response.status_code == 200
    assert "Import poczty ju" in response.text


def test_dashboard_ignores_invalid_mail_import_query_values(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/?mail_imported=abc&mail_skipped=-2&mail_failed=xyz")

    assert response.status_code == 200
    assert "Import poczty zako" not in response.text


def test_get_case_workspace_returns_http_200_and_displays_case_workspace(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _save_case(settings.database_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "CASE-000001" in response.text
    assert "<h1>CASE-000001</h1>" in response.text
    assert "open" in response.text
    assert "Created" in response.text
    assert "Imported" in response.text
    assert "No artifacts" in response.text
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in response.text


def test_get_case_workspace_displays_artifact(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _save_case(settings.database_path, with_artifact=True)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "PDF" in response.text
    assert "artifacts/aa/bb/document.pdf" in response.text


def test_get_case_workspace_returns_404_for_missing_case(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 404


def test_get_case_workspace_returns_404_for_invalid_identifier(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/not-a-uuid")

    assert response.status_code == 404


def test_create_app_uses_passed_database_path(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _save_case(settings.database_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "CASE-000001" in response.text


def test_web_app_works_independently_of_current_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    _save_case(settings.database_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "CASE-000001" in response.text


def test_dashboard_and_case_workspace_use_same_configured_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    _save_case(settings.database_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    with TestClient(create_app(settings)) as client:
        dashboard_response = client.get("/")
        workspace_response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert dashboard_response.status_code == 200
    assert workspace_response.status_code == 200
    assert "CASE-000001" in dashboard_response.text
    assert "CASE-000001" in workspace_response.text


def test_post_import_mail_calls_service_and_redirects_with_result(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    service = _FakeMailImportService(result=MailImportResult(imported=3, skipped=12, failed=1))
    app.state.mail_import_service = service

    with TestClient(app) as client:
        response = client.post("/admin/import-mail", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?mail_imported=3&mail_skipped=12&mail_failed=1"
    assert service.calls == 1


def test_post_import_mail_returns_503_without_configuration(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.post("/admin/import-mail", follow_redirects=False)

    assert response.status_code == 503
    assert response.text == "IMAP import is not configured"


def test_post_import_mail_redirects_with_error_when_service_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    app.state.mail_import_service = _FakeMailImportService(exception=RuntimeError("secret imap failure"))

    with TestClient(app) as client, caplog.at_level("ERROR"):
        response = client.post("/admin/import-mail", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?mail_import_error=1"
    assert "secret imap failure" not in response.text
    assert "Manual IMAP import failed" in caplog.text


def test_post_import_mail_returns_busy_redirect_when_lock_is_held(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    app.state.mail_import_service = _FakeMailImportService()

    with TestClient(app) as client:
        acquired = app.state.mail_import_lock.acquire(blocking=False)
        assert acquired is True
        try:
            response = client.post("/admin/import-mail", follow_redirects=False)
        finally:
            app.state.mail_import_lock.release()

    assert response.status_code == 303
    assert response.headers["location"] == "/?mail_import_busy=1"


def test_post_import_mail_releases_lock_after_success(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    app.state.mail_import_service = _FakeMailImportService(result=MailImportResult(imported=1, skipped=0, failed=0))

    with TestClient(app) as client:
        response = client.post("/admin/import-mail", follow_redirects=False)
        reacquired = app.state.mail_import_lock.acquire(blocking=False)
        assert reacquired is True
        app.state.mail_import_lock.release()

    assert response.status_code == 303


def test_post_import_mail_releases_lock_after_exception(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    app.state.mail_import_service = _FakeMailImportService(exception=RuntimeError("boom"))

    with TestClient(app) as client:
        response = client.post("/admin/import-mail", follow_redirects=False)
        reacquired = app.state.mail_import_lock.acquire(blocking=False)
        assert reacquired is True
        app.state.mail_import_lock.release()

    assert response.status_code == 303
    assert response.headers["location"] == "/?mail_import_error=1"


def test_second_import_can_run_after_first_finishes(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    service = _FakeMailImportService(result=MailImportResult(imported=1, skipped=0, failed=0))
    app.state.mail_import_service = service

    with TestClient(app) as client:
        first_response = client.post("/admin/import-mail", follow_redirects=False)
        second_response = client.post("/admin/import-mail", follow_redirects=False)

    assert first_response.status_code == 303
    assert second_response.status_code == 303
    assert service.calls == 2


def test_dashboard_shows_new_cases_after_manual_import_redirect(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)

    def persist_case() -> None:
        number_provider = SQLiteCaseNumberProvider(database_path=settings.database_path)
        next_number = number_provider.next_number()
        number_provider.close()
        _save_case(
            settings.database_path,
            case_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            reference_number=next_number,
        )

    app.state.mail_import_service = _FakeMailImportService(
        result=MailImportResult(imported=1, skipped=0, failed=0),
        on_call=persist_case,
    )

    with TestClient(app) as client:
        response = client.post("/admin/import-mail", follow_redirects=True)

    assert response.status_code == 200
    assert "Import poczty zako" in response.text
    assert "CASE-000001" in response.text
