from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
import time

import pytest
from fastapi.testclient import TestClient

from aioffice.application import ArtifactRecord, MailImportResult
from aioffice.domain import Artifact, ArtifactType, Case, Identifier, StorageReference
from aioffice.infrastructure import (
    AppSettings,
    MailImportPoller,
    MailPollStatus,
    SQLiteCaseNumberProvider,
    SQLiteCaseRepository,
)
from aioffice.infrastructure.web.app import create_app


def wait_until(predicate: Callable[[], bool], timeout: float = 1.0, interval: float = 0.01) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    msg = "Condition was not met before timeout"
    raise AssertionError(msg)


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


@dataclass(slots=True)
class _FakePoller:
    interval_seconds: float
    status: MailPollStatus

    def get_status(self) -> MailPollStatus:
        return self.status


def _settings(
    tmp_path: Path,
    *,
    with_imap: bool = False,
    polling_enabled: bool = False,
    polling_interval_seconds: int = 300,
    polling_run_immediately: bool = False,
) -> AppSettings:
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
        imap_polling_enabled=polling_enabled,
        imap_polling_interval_seconds=polling_interval_seconds,
        imap_polling_run_immediately=polling_run_immediately,
    )


def _save_case(
    database_path: Path,
    *,
    case_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    reference_number: int = 1,
    artifact_records: tuple[ArtifactRecord, ...] | None = None,
) -> None:
    repository = SQLiteCaseRepository(database_path=database_path)
    case = Case(id=Identifier.from_string(case_id))
    if artifact_records is not None:
        for record in artifact_records:
            case.add_artifact(record.artifact)
    repository.save(case, reference_number=reference_number, artifact_records=artifact_records)
    repository.close()


def _artifact_record(
    *,
    artifact_type: ArtifactType,
    locator: str,
    display_name: str,
    content_type: str | None,
) -> ArtifactRecord:
    return ArtifactRecord(
        artifact=Artifact(
            artifact_type=artifact_type,
            storage_reference=StorageReference(storage_name="filesystem", locator=locator),
        ),
        display_name=display_name,
        content_type=content_type,
    )


def _write_artifact(root_directory: Path, locator: str, content: bytes) -> None:
    artifact_path = root_directory / Path(locator)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(content)


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


def test_dashboard_shows_polling_disabled_by_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Automatyczny import poczty: wy" in response.text


def test_dashboard_shows_active_polling_status_and_interval(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    app.state.mail_import_poller = _FakePoller(
        interval_seconds=300,
        status=MailPollStatus(
            running=True,
            last_started_at=None,
            last_finished_at=None,
            last_success_at=None,
            last_result=None,
            last_error=None,
        ),
    )

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Automatyczny import poczty: aktywny" in response.text
    assert "Interwa" in response.text
    assert "300 sekund" in response.text


def test_dashboard_shows_last_polling_result(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    app.state.mail_import_poller = _FakePoller(
        interval_seconds=300,
        status=MailPollStatus(
            running=True,
            last_started_at=datetime(2026, 7, 23, 10, 0, tzinfo=UTC),
            last_finished_at=datetime(2026, 7, 23, 10, 1, tzinfo=UTC),
            last_success_at=datetime(2026, 7, 23, 10, 1, tzinfo=UTC),
            last_result=MailImportResult(imported=2, skipped=14, failed=0),
            last_error=None,
        ),
    )

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Ostatni import: zaimportowano 2" in response.text
    assert "pomini" in response.text
    assert "b" in response.text


def test_dashboard_shows_generic_polling_error_without_raw_exception(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    app.state.mail_import_poller = _FakePoller(
        interval_seconds=300,
        status=MailPollStatus(
            running=True,
            last_started_at=datetime(2026, 7, 23, 10, 0, tzinfo=UTC),
            last_finished_at=datetime(2026, 7, 23, 10, 1, tzinfo=UTC),
            last_success_at=None,
            last_result=None,
            last_error="IMAP import failed",
        ),
    )

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Ostatni automatyczny import zako" in response.text
    assert "secret imap failure" not in response.text


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
    assert "<h1>Sprawa CASE-000001</h1>" in response.text
    assert "open" in response.text
    assert "Created" in response.text
    assert "Imported" in response.text
    assert "No artifacts" in response.text
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in response.text


def test_get_case_workspace_displays_artifact(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    record = _artifact_record(
        artifact_type=ArtifactType.PDF,
        locator="artifacts/aa/bb/document.pdf",
        display_name="document.pdf",
        content_type="application/pdf",
    )
    _write_artifact(settings.data_directory, record.artifact.storage_reference.locator, b"%PDF")
    _save_case(settings.database_path, artifact_records=(record,))

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "PDF" in response.text
    assert "document.pdf" in response.text
    assert 'href="/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifacts/0/download"' in response.text
    assert "artifacts/aa/bb/document.pdf" not in response.text


def test_get_case_workspace_displays_all_mail_artifacts_in_order(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    records = (
        _artifact_record(
            artifact_type=ArtifactType.EMAIL,
            locator="artifacts/aa/bb/message.eml",
            display_name="message.eml",
            content_type="message/rfc822",
        ),
        _artifact_record(
            artifact_type=ArtifactType.TEXT,
            locator="artifacts/aa/bb/message.txt",
            display_name="message.txt",
            content_type="text/plain; charset=utf-8",
        ),
        _artifact_record(
            artifact_type=ArtifactType.ATTACHMENT,
            locator="artifacts/aa/bb/attachment.pdf",
            display_name="invoice.pdf",
            content_type="application/pdf",
        ),
    )
    _write_artifact(settings.data_directory, "artifacts/aa/bb/message.txt", b"Hello body")
    _save_case(settings.database_path, artifact_records=records)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    email_position = response.text.index("EMAIL")
    text_position = response.text.index("TEXT")
    attachment_position = response.text.index("ATTACHMENT")
    assert email_position < text_position < attachment_position
    assert "message.eml" in response.text
    assert "message.txt" in response.text
    assert "invoice.pdf" in response.text
    assert "Hello body" in response.text


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


def test_case_workspace_escapes_email_html_and_preserves_line_breaks(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    text_record = _artifact_record(
        artifact_type=ArtifactType.TEXT,
        locator="artifacts/aa/bb/message.txt",
        display_name="message.txt",
        content_type="text/plain; charset=utf-8",
    )
    _write_artifact(
        settings.data_directory,
        text_record.artifact.storage_reference.locator,
        b'<script>alert("x")</script>\nSecond line',
    )
    _save_case(settings.database_path, artifact_records=(text_record,))

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "Treść wiadomości" in response.text
    assert "&lt;script&gt;alert" in response.text
    assert "<script>alert(" not in response.text
    assert "Second line" in response.text


def test_case_workspace_hides_email_section_when_text_artifact_is_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    record = _artifact_record(
        artifact_type=ArtifactType.PDF,
        locator="artifacts/aa/bb/document.pdf",
        display_name="document.pdf",
        content_type="application/pdf",
    )
    _write_artifact(settings.data_directory, record.artifact.storage_reference.locator, b"%PDF")
    _save_case(settings.database_path, artifact_records=(record,))

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "Treść wiadomości" not in response.text


def test_case_workspace_shows_neutral_message_for_large_email_body(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    text_record = _artifact_record(
        artifact_type=ArtifactType.TEXT,
        locator="artifacts/aa/bb/message.txt",
        display_name="message.txt",
        content_type="text/plain; charset=utf-8",
    )
    _write_artifact(
        settings.data_directory,
        text_record.artifact.storage_reference.locator,
        b"x" * (1024 * 1024 + 1),
    )
    _save_case(settings.database_path, artifact_records=(text_record,))

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "Treść wiadomości jest zbyt duża do wyświetlenia." in response.text


def test_download_artifact_returns_txt_file_with_safe_headers(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    text_record = _artifact_record(
        artifact_type=ArtifactType.TEXT,
        locator="artifacts/aa/bb/message.txt",
        display_name="faktura lipiec.pdf",
        content_type="text/plain; charset=utf-8",
    )
    _write_artifact(settings.data_directory, text_record.artifact.storage_reference.locator, b"hello")
    _save_case(settings.database_path, artifact_records=(text_record,))

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifacts/0/download")

    assert response.status_code == 200
    assert response.content == b"hello"
    assert response.headers["content-type"].startswith("text/plain; charset=utf-8")
    assert "attachment;" in response.headers["content-disposition"]
    assert 'filename="faktura lipiec.pdf"' in response.headers["content-disposition"]


@pytest.mark.parametrize(
    ("display_name", "expected_ascii_fragment"),
    (
        ("faktura.pdf", 'filename="faktura.pdf"'),
        ("faktura lipiec.pdf", 'filename="faktura lipiec.pdf"'),
        ("zażółć-gęślą.pdf", 'filename="za____-g__l_.pdf"'),
        ('evil"file.pdf', 'filename="evil_file.pdf"'),
        ("../secret.txt", 'filename="__secret.txt"'),
    ),
)
def test_download_artifact_builds_safe_content_disposition(
    tmp_path: Path,
    display_name: str,
    expected_ascii_fragment: str,
) -> None:
    settings = _settings(tmp_path)
    record = _artifact_record(
        artifact_type=ArtifactType.ATTACHMENT,
        locator="artifacts/aa/bb/blob.bin",
        display_name=display_name,
        content_type="application/octet-stream",
    )
    _write_artifact(settings.data_directory, record.artifact.storage_reference.locator, b"blob")
    _save_case(settings.database_path, artifact_records=(record,))

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifacts/0/download")

    assert response.status_code == 200
    assert expected_ascii_fragment in response.headers["content-disposition"]
    assert "\r" not in response.headers["content-disposition"]
    assert "\n" not in response.headers["content-disposition"]


def test_download_artifact_returns_404_for_missing_case(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifacts/0/download")

    assert response.status_code == 404


def test_download_artifact_returns_404_for_invalid_identifier(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/not-a-uuid/artifacts/0/download")

    assert response.status_code == 404


def test_download_artifact_returns_404_for_negative_position(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifacts/-1/download")

    assert response.status_code == 404


def test_download_artifact_returns_404_for_missing_physical_file_without_leaking_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _settings(tmp_path)
    record = _artifact_record(
        artifact_type=ArtifactType.PDF,
        locator="artifacts/aa/bb/missing.pdf",
        display_name="missing.pdf",
        content_type="application/pdf",
    )
    _save_case(settings.database_path, artifact_records=(record,))

    with TestClient(create_app(settings)) as client, caplog.at_level("WARNING"):
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifacts/0/download")

    assert response.status_code == 404
    assert str(settings.data_directory) not in response.text
    assert "Artifact file is missing" in caplog.text
    assert str(settings.data_directory) not in caplog.text


def test_download_artifact_returns_404_for_path_traversal_locator(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    traversal_record = _artifact_record(
        artifact_type=ArtifactType.ATTACHMENT,
        locator="../secret.txt",
        display_name="secret.txt",
        content_type="text/plain",
    )
    _save_case(settings.database_path, artifact_records=(traversal_record,))
    secret_path = tmp_path / "secret.txt"
    secret_path.write_text("secret")

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifacts/0/download")

    assert response.status_code == 404
    assert response.text != "secret"


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


def test_create_app_rejects_polling_enabled_without_imap_configuration(tmp_path: Path) -> None:
    settings = _settings(tmp_path, polling_enabled=True)

    with pytest.raises(ValueError, match="IMAP polling requires IMAP configuration"):
        create_app(settings)


def test_create_app_does_not_start_poller_during_build(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True, polling_enabled=True)
    app = create_app(settings)

    poller = app.state.mail_import_poller

    assert poller is not None
    assert poller.is_running is False


def test_create_app_builds_poller_when_polling_enabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True, polling_enabled=True)
    app = create_app(settings)

    assert app.state.mail_import_poller is not None


def test_create_app_uses_same_lock_for_manual_endpoint_and_poller(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True, polling_enabled=True)
    app = create_app(settings)

    poller = app.state.mail_import_poller

    assert poller is not None
    assert poller.import_lock is app.state.mail_import_lock


def test_poller_starts_and_stops_with_lifespan(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        with_imap=True,
        polling_enabled=True,
        polling_interval_seconds=30,
    )
    app = create_app(settings)
    poller = app.state.mail_import_poller
    assert poller is not None
    assert poller.is_running is False

    with TestClient(app):
        assert poller.is_running is True

    assert poller.is_running is False


def test_manual_import_returns_busy_while_automatic_import_holds_lock(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_imap=True)
    app = create_app(settings)
    release_event = Event()

    def hold_import_open() -> None:
        release_event.wait(1.0)

    fake_service = _FakeMailImportService(
        result=MailImportResult(imported=1, skipped=0, failed=0),
        on_call=hold_import_open,
    )
    poller = MailImportPoller(
        import_service=fake_service,
        import_lock=app.state.mail_import_lock,
        interval_seconds=30.0,
        run_immediately=True,
    )
    app.state.mail_import_service = fake_service
    app.state.mail_import_poller = poller

    with TestClient(app) as client:
        poller.start()
        try:
            wait_until(lambda: fake_service.calls >= 1)
            response = client.post("/admin/import-mail", follow_redirects=False)
        finally:
            release_event.set()
            poller.stop()

    assert response.status_code == 303
    assert response.headers["location"] == "/?mail_import_busy=1"
