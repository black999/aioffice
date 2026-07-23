import logging
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from aioffice.application import (
    PersistedReplyDraft,
    ReplyDraftGenerationResult,
    ReplyDraftStatus,
)
from aioffice.domain import Case, Identifier
from aioffice.infrastructure import AppSettings, SQLiteCaseRepository, SQLiteReplyDraftRepository
from aioffice.infrastructure.web.app import create_app


@dataclass(slots=True)
class _FakeReplyDraftGenerationService:
    result: ReplyDraftGenerationResult | None = None
    exception: Exception | None = None
    seen_force: bool | None = None
    seen_instruction: str | None = None
    calls: int = 0

    def generate_reply_draft(
        self,
        case_id: Identifier,
        *,
        operator_instruction: str | None = None,
        force: bool = False,
    ):
        self.calls += 1
        self.seen_force = force
        self.seen_instruction = operator_instruction
        if self.exception is not None:
            raise self.exception
        return self.result


@dataclass(slots=True)
class _FakeReplyDraftEditingService:
    result: PersistedReplyDraft | None = None
    exception: Exception | None = None
    seen_subject: str | None = None
    seen_body: str | None = None

    def update_reply_draft(self, case_id: Identifier, *, subject: str, body: str):
        self.seen_subject = subject
        self.seen_body = body
        if self.exception is not None:
            raise self.exception
        return self.result


@dataclass(slots=True)
class _FakeReplyDraftApprovalService:
    result: PersistedReplyDraft | None = None
    exception: Exception | None = None
    seen_approved_by: str | None = None
    revoke_calls: int = 0

    def approve_reply_draft(self, case_id: Identifier, *, approved_by: str):
        self.seen_approved_by = approved_by
        if self.exception is not None:
            raise self.exception
        return self.result

    def revoke_reply_draft_approval(self, case_id: Identifier):
        self.revoke_calls += 1
        if self.exception is not None:
            raise self.exception
        return self.result


def _settings(tmp_path: Path, *, enabled: bool = False) -> AppSettings:
    return AppSettings(
        data_directory=tmp_path / "storage",
        database_path=tmp_path / "storage" / "aioffice.db",
        artifacts_directory=tmp_path / "storage" / "artifacts",
        incoming_directory=tmp_path / "storage" / "incoming",
        processed_directory=tmp_path / "storage" / "processed",
        host="127.0.0.1",
        port=8000,
        ai_reply_draft_enabled=enabled,
    )


def _save_case(database_path: Path) -> None:
    repository = SQLiteCaseRepository(database_path=database_path)
    repository.save(
        Case(id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        reference_number=1,
    )
    repository.close()


def _draft(
    *,
    status: ReplyDraftStatus = ReplyDraftStatus.GENERATED,
    approved_by: str | None = None,
    approved_at: str | None = None,
) -> PersistedReplyDraft:
    return PersistedReplyDraft(
        case_id=Identifier.from_string("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        subject='Temat <script>alert("x")</script>',
        body='Tresc <script>alert("x")</script>',
        status=status,
        model_name="qwen3:4b",
        operator_instruction="Uprzejmie",
        approved_by=approved_by,
        approved_at=approved_at,
        created_at="2026-07-23T10:00:00+00:00",
        updated_at="2026-07-23T10:00:00+00:00",
    )


def test_reply_draft_endpoint_returns_503_when_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=False)
    _save_case(settings.database_path)

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/generate",
            data={"operator_instruction": "Uprzejmie"},
            follow_redirects=False,
        )

    assert response.status_code == 503
    assert response.text == "AI reply draft generation is not configured"


def test_reply_draft_generate_redirects_with_success_and_passes_force(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    fake_service = _FakeReplyDraftGenerationService(
        result=ReplyDraftGenerationResult(draft=_draft(), skipped=False, reason=None)
    )
    app.state.reply_draft_generation_service = fake_service

    with TestClient(app) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/generate",
            data={"operator_instruction": "  Uprzejmie  ", "force": "true"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_success=1"
    )
    assert fake_service.seen_force is True
    assert fake_service.seen_instruction == "  Uprzejmie  "


def test_reply_draft_generate_returns_404_for_invalid_identifier(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    app = create_app(settings)
    app.state.reply_draft_generation_service = _FakeReplyDraftGenerationService(
        result=ReplyDraftGenerationResult(draft=_draft(), skipped=False, reason=None)
    )

    with TestClient(app) as client:
        response = client.post("/cases/not-a-uuid/reply-draft/generate", follow_redirects=False)

    assert response.status_code == 404


def test_reply_draft_generate_redirects_when_busy(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    app.state.reply_draft_generation_service = _FakeReplyDraftGenerationService(
        result=ReplyDraftGenerationResult(draft=_draft(), skipped=False, reason=None)
    )

    with TestClient(app) as client:
        acquired = app.state.reply_draft_generation_lock.acquire(blocking=False)
        assert acquired is True
        try:
            response = client.post(
                "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/generate",
                follow_redirects=False,
            )
        finally:
            app.state.reply_draft_generation_lock.release()

    assert response.status_code == 303
    assert response.headers["location"] == "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_busy=1"


def test_reply_draft_save_redirects_on_success(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    app.state.reply_draft_editing_service = _FakeReplyDraftEditingService(result=_draft())

    with TestClient(app) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/save",
            data={"subject": "Nowy temat", "body": "Nowa tresc"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_saved=1"


def test_reply_draft_approval_redirects_on_success(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    fake_service = _FakeReplyDraftApprovalService(
        result=_draft(
            status=ReplyDraftStatus.APPROVED,
            approved_by="Jan Kowalski",
            approved_at="2026-07-23T10:05:00+00:00",
        )
    )
    app.state.reply_draft_approval_service = fake_service

    with TestClient(app) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/approve",
            data={"approved_by": "Jan Kowalski"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approved=1"
    )
    assert fake_service.seen_approved_by == "Jan Kowalski"


def test_reply_draft_approval_returns_404_for_invalid_identifier(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    app = create_app(settings)
    app.state.reply_draft_approval_service = _FakeReplyDraftApprovalService(result=_draft())

    with TestClient(app) as client:
        response = client.post(
            "/cases/not-a-uuid/reply-draft/approve",
            data={"approved_by": "Jan Kowalski"},
            follow_redirects=False,
        )

    assert response.status_code == 404


def test_reply_draft_approval_returns_404_when_draft_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    app.state.reply_draft_approval_service = _FakeReplyDraftApprovalService(result=None)

    with TestClient(app) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/approve",
            data={"approved_by": "Jan Kowalski"},
            follow_redirects=False,
        )

    assert response.status_code == 404


def test_reply_draft_approval_redirects_on_validation_error_without_exposing_name(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    app.state.reply_draft_approval_service = _FakeReplyDraftApprovalService(
        exception=ValueError("bad approver"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/approve",
            data={"approved_by": "Jan Kowalski"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approval_validation_error=1"
    )
    assert "Jan%20Kowalski" not in response.headers["location"]


def test_reply_draft_approval_redirects_on_persistence_error_without_exposing_name(
    tmp_path: Path,
    caplog,
) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    app.state.reply_draft_approval_service = _FakeReplyDraftApprovalService(
        exception=RuntimeError("sqlite exploded"),
    )

    with caplog.at_level(logging.ERROR):
        with TestClient(app) as client:
            response = client.post(
                "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/approve",
                data={"approved_by": "Jan Kowalski"},
                follow_redirects=False,
            )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approval_error=1"
    )
    assert "sqlite exploded" not in response.text
    assert "Jan Kowalski" not in caplog.text


def test_reply_draft_revoke_redirects_on_success(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    app.state.reply_draft_approval_service = _FakeReplyDraftApprovalService(
        result=_draft(status=ReplyDraftStatus.EDITED),
    )

    with TestClient(app) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/revoke-approval",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approval_revoked=1"
    )


def test_reply_draft_revoke_returns_404_for_invalid_identifier(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    app = create_app(settings)
    app.state.reply_draft_approval_service = _FakeReplyDraftApprovalService(result=_draft())

    with TestClient(app) as client:
        response = client.post("/cases/not-a-uuid/reply-draft/revoke-approval", follow_redirects=False)

    assert response.status_code == 404


def test_reply_draft_revoke_returns_404_when_draft_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    app.state.reply_draft_approval_service = _FakeReplyDraftApprovalService(result=None)

    with TestClient(app) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/revoke-approval",
            follow_redirects=False,
        )

    assert response.status_code == 404


def test_reply_draft_revoke_redirects_on_persistence_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    app = create_app(settings)
    app.state.reply_draft_approval_service = _FakeReplyDraftApprovalService(
        exception=RuntimeError("boom"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/reply-draft/revoke-approval",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approval_error=1"
    )


def test_case_workspace_shows_generation_form_when_draft_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "Projekt odpowiedzi" in response.text
    assert "Wygeneruj projekt odpowiedzi" in response.text
    assert 'maxlength="2000"' in response.text


def test_case_workspace_shows_disabled_message_when_feature_is_off(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=False)
    _save_case(settings.database_path)

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "Generator projektu odpowiedzi nie jest skonfigurowany." in response.text


def test_case_workspace_shows_saved_generated_draft_with_approval_form_and_escaped_xss(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    repository = SQLiteReplyDraftRepository(database_path=settings.database_path)
    repository.save(_draft())
    repository.close()

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "Zapisz zmiany" in response.text
    assert "Wygeneruj ponownie" in response.text
    assert "Osoba zatwierdzająca" in response.text
    assert "Zatwierdź projekt" in response.text
    assert "Podana osoba nie jest weryfikowana przez system logowania." in response.text
    assert "Status: Wygenerowany" in response.text
    assert "&lt;script&gt;alert" in response.text
    assert '<script>alert("x")</script>' not in response.text


def test_case_workspace_shows_approved_draft_details_and_revoke_action(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    repository = SQLiteReplyDraftRepository(database_path=settings.database_path)
    repository.save(
        _draft(
            status=ReplyDraftStatus.APPROVED,
            approved_by='<script>alert("x")</script>',
            approved_at="2026-07-23T10:05:00+00:00",
        )
    )
    repository.close()

    with TestClient(create_app(settings)) as client:
        response = client.get("/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert response.status_code == 200
    assert "Status: Zatwierdzony" in response.text
    assert "Data zatwierdzenia: 2026-07-23T10:05:00+00:00" in response.text
    assert "Cofnij zatwierdzenie" in response.text
    assert "Zatwierdź projekt" not in response.text
    assert "Zmiana tematu lub treści usunie obecne zatwierdzenie." in response.text
    assert "Ponowne generowanie zastąpi bieżący projekt i usunie zatwierdzenie." in response.text
    assert "&lt;script&gt;alert" in response.text
    assert '<script>alert("x")</script>' not in response.text


def test_case_workspace_shows_reply_draft_ui_messages(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    repository = SQLiteReplyDraftRepository(database_path=settings.database_path)
    repository.save(_draft())
    repository.close()

    with TestClient(create_app(settings)) as client:
        approved = client.get(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approved=1"
        )
        revoked = client.get(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approval_revoked=1"
        )
        validation = client.get(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approval_validation_error=1"
        )
        error = client.get(
            "/cases/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?reply_draft_approval_error=1"
        )

    assert "Projekt odpowiedzi został zatwierdzony." in approved.text
    assert "Zatwierdzenie projektu zostało cofnięte." in revoked.text
    assert "Nieprawidłowa nazwa osoby zatwierdzającej." in validation.text
    assert "Nie udało się zmienić zatwierdzenia projektu." in error.text


def test_dashboard_shows_reply_draft_statuses(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True)
    _save_case(settings.database_path)
    repository = SQLiteReplyDraftRepository(database_path=settings.database_path)
    repository.save(
        _draft(
            status=ReplyDraftStatus.APPROVED,
            approved_by="Jan Kowalski",
            approved_at="2026-07-23T10:05:00+00:00",
        )
    )
    repository.close()

    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Zatwierdzony" in response.text
