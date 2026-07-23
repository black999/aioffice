"""FastAPI application bootstrap."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import Iterator
from pathlib import Path
from threading import Lock
from typing import AsyncIterator
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates

from aioffice.application import (
    CaseClassificationError,
    CaseFactory,
    MailImportResult,
    ReplyDraftGenerationError,
    sanitize_display_name,
)
from aioffice.application.services import (
    ArtifactDownloadService,
    CaseClassificationService,
    CaseDashboardService,
    CaseWorkspaceService,
    DocumentExtractionService,
    DocumentImportService,
    MailImportService,
    ReplyDraftApprovalService,
    ReplyDraftEditingService,
    ReplyDraftGenerationService,
)
from aioffice.application.storage import ArtifactNotFoundError, UnsupportedStorageError
from aioffice.domain import Identifier
from aioffice.infrastructure import (
    AppSettings,
    DOCXTextExtractor,
    FilesystemStorage,
    IMAPMailboxClient,
    MailImportPoller,
    MailPollStatus,
    OllamaCaseClassifier,
    OllamaReplyDraftGenerator,
    PDFTextExtractor,
    SQLiteCaseClassificationRepository,
    SQLiteCaseNumberProvider,
    SQLiteCaseRepository,
    SQLiteImportedMailRepository,
    SQLiteReplyDraftRepository,
    StandardLibraryMailContentParser,
    WatchFolder,
)


_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
logger = logging.getLogger(__name__)


def _parse_non_negative_int(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    try:
        parsed_value = int(raw_value)
    except ValueError:
        return None
    if parsed_value < 0:
        return 0
    return parsed_value


def _build_mail_import_message(request: Request) -> str | None:
    if request.query_params.get("mail_import_error") == "1":
        return "Nie udało się uruchomić importu poczty."
    if request.query_params.get("mail_import_busy") == "1":
        return "Import poczty już trwa."

    imported = _parse_non_negative_int(request.query_params.get("mail_imported"))
    skipped = _parse_non_negative_int(request.query_params.get("mail_skipped"))
    failed = _parse_non_negative_int(request.query_params.get("mail_failed"))
    if imported is None or skipped is None or failed is None:
        return None

    return (
        "Import poczty zakończony. "
        f"Zaimportowano: {imported}, pominięto: {skipped}, błędy: {failed}."
    )


def _build_mail_import_redirect(result: MailImportResult) -> RedirectResponse:
    return RedirectResponse(
        url=(
            "/"
            f"?mail_imported={result.imported}"
            f"&mail_skipped={result.skipped}"
            f"&mail_failed={result.failed}"
        ),
        status_code=303,
    )


def _build_extraction_message(request: Request) -> str | None:
    if request.query_params.get("extract_error") == "1":
        return "Nie udało się uruchomić ekstrakcji tekstu z dokumentów."

    extracted = _parse_non_negative_int(request.query_params.get("extracted"))
    skipped = _parse_non_negative_int(request.query_params.get("skipped"))
    failed = _parse_non_negative_int(request.query_params.get("failed"))
    if extracted is None or skipped is None or failed is None:
        return None
    if extracted == 0 and failed == 0 and skipped > 0:
        return f"Tekst został już wcześniej wyodrębniony. Pominięto: {skipped}."
    return (
        "Ekstrakcja zakończona. "
        f"Wyodrębniono: {extracted}, pominięto: {skipped}, błędy: {failed}."
    )


def _build_classification_message(request: Request) -> str | None:
    if request.query_params.get("classification_success") == "1":
        return "Klasyfikacja sprawy zakończona."
    if request.query_params.get("classification_skipped") == "1":
        return "Sprawa została już sklasyfikowana."
    if request.query_params.get("classification_no_text") == "1":
        return "Brak użytecznego tekstu do klasyfikacji sprawy."
    if request.query_params.get("classification_error") == "1":
        return "Nie udało się sklasyfikować sprawy."
    if request.query_params.get("classification_busy") == "1":
        return "Klasyfikacja już trwa."
    return None


def _build_reply_draft_message_legacy(request: Request) -> str | None:
    if request.query_params.get("reply_draft_success") == "1":
        return "Projekt odpowiedzi zostaĹ‚ wygenerowany."
    if request.query_params.get("reply_draft_skipped") == "1":
        return "Projekt odpowiedzi juĹĽ istnieje."
    if request.query_params.get("reply_draft_no_text") == "1":
        return "Brak uĹĽytecznego tekstu do wygenerowania projektu odpowiedzi."
    if request.query_params.get("reply_draft_error") == "1":
        return "Nie udaĹ‚o siÄ™ wygenerowaÄ‡ projektu odpowiedzi."
    if request.query_params.get("reply_draft_validation_error") == "1":
        return "NieprawidĹ‚owe dane projektu odpowiedzi."
    if request.query_params.get("reply_draft_busy") == "1":
        return "Generowanie projektu odpowiedzi juĹĽ trwa."
    if request.query_params.get("reply_draft_saved") == "1":
        return "Projekt odpowiedzi zostaĹ‚ zapisany."
    return None


def _build_mail_polling_snapshot(
    poller: MailImportPoller | None,
) -> tuple[bool, int | None, MailPollStatus | None]:
    if poller is None:
        return False, None, None
    return True, int(poller.interval_seconds), poller.get_status()


def _build_reply_draft_message(request: Request) -> str | None:
    if request.query_params.get("reply_draft_success") == "1":
        return "Projekt odpowiedzi został wygenerowany."
    if request.query_params.get("reply_draft_skipped") == "1":
        return "Projekt odpowiedzi już istnieje."
    if request.query_params.get("reply_draft_no_text") == "1":
        return "Brak użytecznego tekstu do wygenerowania projektu odpowiedzi."
    if request.query_params.get("reply_draft_error") == "1":
        return "Nie udało się wygenerować projektu odpowiedzi."
    if request.query_params.get("reply_draft_validation_error") == "1":
        return "Nieprawidłowe dane projektu odpowiedzi."
    if request.query_params.get("reply_draft_busy") == "1":
        return "Generowanie projektu odpowiedzi już trwa."
    if request.query_params.get("reply_draft_saved") == "1":
        return "Projekt odpowiedzi został zapisany."
    if request.query_params.get("reply_draft_approved") == "1":
        return "Projekt odpowiedzi został zatwierdzony."
    if request.query_params.get("reply_draft_approval_revoked") == "1":
        return "Zatwierdzenie projektu zostało cofnięte."
    if request.query_params.get("reply_draft_approval_validation_error") == "1":
        return "Nieprawidłowa nazwa osoby zatwierdzającej."
    if request.query_params.get("reply_draft_approval_error") == "1":
        return "Nie udało się zmienić zatwierdzenia projektu."
    return None


def _build_content_disposition(display_name: str) -> str:
    safe_display_name = sanitize_display_name(display_name, fallback="download.bin")
    ascii_name = "".join(
        character
        if character.isascii() and character.isprintable() and character not in {'"', "\\", ";", "/", ":"}
        else "_"
        for character in safe_display_name
    ).strip(" .")
    if not ascii_name:
        ascii_name = "download.bin"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(safe_display_name)}'


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create the FastAPI application."""

    if settings is None:
        settings = AppSettings.from_environment()

    repository = SQLiteCaseRepository(database_path=settings.database_path)
    classification_repository = SQLiteCaseClassificationRepository(database_path=settings.database_path)
    reply_draft_repository = SQLiteReplyDraftRepository(database_path=settings.database_path)
    dashboard_service = CaseDashboardService(
        repository=repository,
        classification_repository=classification_repository,
        reply_draft_repository=reply_draft_repository,
    )

    import_repository = SQLiteCaseRepository(database_path=settings.database_path)
    number_provider = SQLiteCaseNumberProvider(database_path=settings.database_path)
    storage = FilesystemStorage(root_directory=settings.data_directory)
    workspace_service = CaseWorkspaceService(
        repository=repository,
        storage_reader=storage,
        classification_repository=classification_repository,
        reply_draft_repository=reply_draft_repository,
    )
    download_service = ArtifactDownloadService(repository=repository, storage_reader=storage)
    extraction_service = DocumentExtractionService(
        repository=import_repository,
        storage=storage,
        storage_reader=storage,
        extractors=(
            PDFTextExtractor(),
            DOCXTextExtractor(max_xml_bytes=settings.document_extraction_max_input_bytes),
        ),
        max_input_bytes=settings.document_extraction_max_input_bytes,
        max_output_chars=settings.document_extraction_max_output_chars,
    )
    import_service = DocumentImportService(
        storage=storage,
        case_factory=CaseFactory(),
        case_repository=import_repository,
        case_number_provider=number_provider,
    )
    case_classifier = (
        OllamaCaseClassifier(
            base_url=settings.ollama_base_url,
            model_name=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        if settings.ai_classification_enabled
        else None
    )
    classification_service = (
        CaseClassificationService(
            case_repository=repository,
            classification_repository=classification_repository,
            storage_reader=storage,
            classifier=case_classifier,
            max_input_chars=settings.ai_classification_max_input_chars,
        )
        if case_classifier is not None
        else None
    )
    reply_draft_generator = (
        OllamaReplyDraftGenerator(
            base_url=settings.ollama_base_url,
            model_name=settings.reply_draft_model or settings.ollama_model,
            timeout_seconds=settings.reply_draft_timeout_seconds,
        )
        if settings.ai_reply_draft_enabled
        else None
    )
    reply_draft_generation_service = (
        ReplyDraftGenerationService(
            case_repository=repository,
            classification_repository=classification_repository,
            reply_draft_repository=reply_draft_repository,
            storage_reader=storage,
            generator=reply_draft_generator,
            max_input_chars=settings.reply_draft_max_input_chars,
            max_operator_instruction_chars=settings.reply_draft_max_operator_instruction_chars,
        )
        if reply_draft_generator is not None
        else None
    )
    reply_draft_editing_service = ReplyDraftEditingService(repository=reply_draft_repository)
    reply_draft_approval_service = ReplyDraftApprovalService(repository=reply_draft_repository)
    watch_folder = WatchFolder(
        watch_directory=settings.incoming_directory,
        processed_directory=settings.processed_directory,
        import_service=import_service,
    )
    imported_mail_repository: SQLiteImportedMailRepository | None = None
    mail_import_service: MailImportService | None = None
    if settings.imap_host is not None and settings.imap_username is not None:
        imported_mail_repository = SQLiteImportedMailRepository(database_path=settings.database_path)
        mail_content_parser = StandardLibraryMailContentParser()
        mailbox_client = IMAPMailboxClient(
            host=settings.imap_host,
            port=settings.imap_port,
            username=settings.imap_username,
            password=settings.imap_password or "",
            mailbox=settings.imap_mailbox,
            use_ssl=settings.imap_use_ssl,
        )
        mail_import_service = MailImportService(
            mailbox_client=mailbox_client,
            imported_mail_repository=imported_mail_repository,
            storage=storage,
            case_factory=CaseFactory(),
            case_repository=import_repository,
            case_number_provider=number_provider,
            mail_content_parser=mail_content_parser,
            imap_max_attachment_bytes=settings.imap_max_attachment_bytes,
            imap_max_attachments_per_message=settings.imap_max_attachments_per_message,
        )
    if settings.imap_polling_enabled and mail_import_service is None:
        msg = "IMAP polling requires IMAP configuration"
        raise ValueError(msg)

    mail_import_lock = Lock()
    classification_lock = Lock()
    reply_draft_generation_lock = Lock()
    mail_import_poller: MailImportPoller | None = None
    if settings.imap_polling_enabled and mail_import_service is not None:
        mail_import_poller = MailImportPoller(
            import_service=mail_import_service,
            import_lock=mail_import_lock,
            interval_seconds=float(settings.imap_polling_interval_seconds),
            run_immediately=settings.imap_polling_run_immediately,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            watch_folder.start()
            if mail_import_poller is not None:
                mail_import_poller.start()
            yield
        finally:
            if mail_import_poller is not None:
                mail_import_poller.stop()
            watch_folder.stop()
            if imported_mail_repository is not None:
                imported_mail_repository.close()
            reply_draft_repository.close()
            classification_repository.close()
            repository.close()
            import_repository.close()
            number_provider.close()

    app = FastAPI(title="AI Office", lifespan=lifespan)
    app.state.mail_import_service = mail_import_service
    app.state.mail_import_lock = mail_import_lock
    app.state.mail_import_poller = mail_import_poller
    app.state.classification_service = classification_service
    app.state.classification_lock = classification_lock
    app.state.ai_classification_enabled = settings.ai_classification_enabled
    app.state.reply_draft_generation_service = reply_draft_generation_service
    app.state.reply_draft_editing_service = reply_draft_editing_service
    app.state.reply_draft_approval_service = reply_draft_approval_service
    app.state.reply_draft_generation_lock = reply_draft_generation_lock
    app.state.ai_reply_draft_enabled = settings.ai_reply_draft_enabled
    app.state.reply_draft_max_operator_instruction_chars = (
        settings.reply_draft_max_operator_instruction_chars
    )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        polling_enabled, polling_interval_seconds, polling_status = _build_mail_polling_snapshot(
            request.app.state.mail_import_poller
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "page_title": "AI Office",
                "case_count": dashboard_service.count_cases(),
                "cases": dashboard_service.list_cases(),
                "mail_import_available": request.app.state.mail_import_service is not None,
                "mail_import_message": _build_mail_import_message(request),
                "mail_polling_enabled": polling_enabled,
                "mail_polling_interval_seconds": polling_interval_seconds,
                "mail_polling_status": polling_status,
            },
        )

    @app.post("/admin/import-mail")
    def import_mail(request: Request) -> Response:
        mail_import_service = request.app.state.mail_import_service
        if mail_import_service is None:
            return PlainTextResponse("IMAP import is not configured", status_code=503)

        import_lock = request.app.state.mail_import_lock
        if not import_lock.acquire(blocking=False):
            return RedirectResponse(url="/?mail_import_busy=1", status_code=303)

        try:
            result = mail_import_service.import_new_messages()
        except Exception:
            logger.exception("Manual IMAP import failed")
            return RedirectResponse(url="/?mail_import_error=1", status_code=303)
        finally:
            import_lock.release()

        return _build_mail_import_redirect(result)

    @app.get("/cases/{case_id}", response_class=HTMLResponse)
    def case_workspace(request: Request, case_id: str) -> HTMLResponse:
        workspace = workspace_service.get_case_workspace(
            case_id,
            extraction_message=_build_extraction_message(request),
            classification_message=_build_classification_message(request),
            reply_draft_message=_build_reply_draft_message(request),
        )
        if workspace is None:
            raise HTTPException(status_code=404)
        return _TEMPLATES.TemplateResponse(
            request,
            "case_workspace.html",
            {
                "page_title": workspace.case_reference,
                "workspace": workspace,
                "classification_enabled": request.app.state.ai_classification_enabled,
                "reply_draft_enabled": request.app.state.ai_reply_draft_enabled,
                "reply_draft_instruction_max_chars": (
                    request.app.state.reply_draft_max_operator_instruction_chars
                ),
            },
        )

    @app.post("/cases/{case_id}/classify")
    def classify_case(case_id: str, request: Request, force: bool = False) -> Response:
        classification_service = request.app.state.classification_service
        if classification_service is None:
            return PlainTextResponse("AI classification is not configured", status_code=503)

        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            raise HTTPException(status_code=404) from None

        classification_lock = request.app.state.classification_lock
        if not classification_lock.acquire(blocking=False):
            return RedirectResponse(url=f"/cases/{case_id}?classification_busy=1", status_code=303)

        try:
            result = classification_service.classify_case(identifier, force=force)
        except CaseClassificationError:
            logger.exception("Case classification failed: case_id=%s", case_id)
            return RedirectResponse(url=f"/cases/{case_id}?classification_error=1", status_code=303)
        except Exception:
            logger.exception("Case classification failed: case_id=%s", case_id)
            return RedirectResponse(url=f"/cases/{case_id}?classification_error=1", status_code=303)
        finally:
            classification_lock.release()

        if result is None:
            raise HTTPException(status_code=404)
        if result.skipped and result.reason == "already_classified":
            return RedirectResponse(url=f"/cases/{case_id}?classification_skipped=1", status_code=303)
        if result.skipped and result.reason == "no_text":
            return RedirectResponse(url=f"/cases/{case_id}?classification_no_text=1", status_code=303)
        return RedirectResponse(url=f"/cases/{case_id}?classification_success=1", status_code=303)

    @app.post("/cases/{case_id}/reply-draft/generate")
    def generate_reply_draft(
        case_id: str,
        request: Request,
        operator_instruction: str = Form(""),
        force: bool = Form(False),
    ) -> Response:
        reply_draft_generation_service = request.app.state.reply_draft_generation_service
        if reply_draft_generation_service is None:
            return PlainTextResponse("AI reply draft generation is not configured", status_code=503)

        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            raise HTTPException(status_code=404) from None

        reply_draft_generation_lock = request.app.state.reply_draft_generation_lock
        if not reply_draft_generation_lock.acquire(blocking=False):
            return RedirectResponse(url=f"/cases/{case_id}?reply_draft_busy=1", status_code=303)

        try:
            result = reply_draft_generation_service.generate_reply_draft(
                identifier,
                operator_instruction=operator_instruction,
                force=force,
            )
        except ValueError:
            return RedirectResponse(
                url=f"/cases/{case_id}?reply_draft_validation_error=1",
                status_code=303,
            )
        except ReplyDraftGenerationError:
            logger.exception("Reply draft generation failed: case_id=%s", case_id)
            return RedirectResponse(url=f"/cases/{case_id}?reply_draft_error=1", status_code=303)
        except Exception:
            logger.exception("Reply draft generation failed: case_id=%s", case_id)
            return RedirectResponse(url=f"/cases/{case_id}?reply_draft_error=1", status_code=303)
        finally:
            reply_draft_generation_lock.release()

        if result is None:
            raise HTTPException(status_code=404)
        if result.skipped and result.reason == "already_generated":
            return RedirectResponse(url=f"/cases/{case_id}?reply_draft_skipped=1", status_code=303)
        if result.skipped and result.reason == "no_text":
            return RedirectResponse(url=f"/cases/{case_id}?reply_draft_no_text=1", status_code=303)
        return RedirectResponse(url=f"/cases/{case_id}?reply_draft_success=1", status_code=303)

    @app.post("/cases/{case_id}/reply-draft/save")
    def save_reply_draft(
        case_id: str,
        request: Request,
        subject: str = Form(...),
        body: str = Form(...),
    ) -> Response:
        reply_draft_editing_service = request.app.state.reply_draft_editing_service

        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            raise HTTPException(status_code=404) from None

        try:
            draft = reply_draft_editing_service.update_reply_draft(
                identifier,
                subject=subject,
                body=body,
            )
        except ValueError:
            return RedirectResponse(
                url=f"/cases/{case_id}?reply_draft_validation_error=1",
                status_code=303,
            )

        if draft is None:
            raise HTTPException(status_code=404)
        return RedirectResponse(url=f"/cases/{case_id}?reply_draft_saved=1", status_code=303)

    @app.post("/cases/{case_id}/reply-draft/approve")
    def approve_reply_draft(
        case_id: str,
        request: Request,
        approved_by: str = Form(...),
    ) -> Response:
        reply_draft_approval_service = request.app.state.reply_draft_approval_service

        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            raise HTTPException(status_code=404) from None

        try:
            draft = reply_draft_approval_service.approve_reply_draft(
                identifier,
                approved_by=approved_by,
            )
        except ValueError:
            return RedirectResponse(
                url=f"/cases/{case_id}?reply_draft_approval_validation_error=1",
                status_code=303,
            )
        except Exception:
            logger.exception("Reply draft approval failed: case_id=%s", case_id)
            return RedirectResponse(
                url=f"/cases/{case_id}?reply_draft_approval_error=1",
                status_code=303,
            )

        if draft is None:
            raise HTTPException(status_code=404)
        return RedirectResponse(url=f"/cases/{case_id}?reply_draft_approved=1", status_code=303)

    @app.post("/cases/{case_id}/reply-draft/revoke-approval")
    def revoke_reply_draft_approval(case_id: str, request: Request) -> Response:
        reply_draft_approval_service = request.app.state.reply_draft_approval_service

        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            raise HTTPException(status_code=404) from None

        try:
            draft = reply_draft_approval_service.revoke_reply_draft_approval(identifier)
        except Exception:
            logger.exception("Reply draft approval failed: case_id=%s", case_id)
            return RedirectResponse(
                url=f"/cases/{case_id}?reply_draft_approval_error=1",
                status_code=303,
            )

        if draft is None:
            raise HTTPException(status_code=404)
        return RedirectResponse(
            url=f"/cases/{case_id}?reply_draft_approval_revoked=1",
            status_code=303,
        )

    @app.post("/cases/{case_id}/extract-documents")
    def extract_documents(case_id: str) -> Response:
        try:
            identifier = Identifier.from_string(case_id)
        except ValueError:
            raise HTTPException(status_code=404) from None

        try:
            result = extraction_service.extract_case_documents(identifier)
        except Exception:
            logger.exception("Document extraction use case failed")
            return RedirectResponse(url=f"/cases/{case_id}?extract_error=1", status_code=303)

        if result is None:
            raise HTTPException(status_code=404)
        return RedirectResponse(
            url=(
                f"/cases/{case_id}"
                f"?extracted={result.extracted}"
                f"&skipped={result.skipped}"
                f"&failed={result.failed}"
            ),
            status_code=303,
        )

    @app.get("/cases/{case_id}/artifacts/{position}/download")
    def download_artifact(case_id: str, position: int) -> Response:
        if position < 0:
            raise HTTPException(status_code=404)

        try:
            opened = download_service.open_artifact(case_id, position)
        except ArtifactNotFoundError:
            logger.warning("Artifact file is missing: case_id=%s position=%s", case_id, position)
            raise HTTPException(status_code=404) from None
        except UnsupportedStorageError:
            logger.exception("Artifact download failed")
            raise HTTPException(status_code=500) from None

        if opened is None:
            raise HTTPException(status_code=404)

        artifact, handle = opened

        def iterator() -> Iterator[bytes]:
            try:
                while chunk := handle.read(1024 * 1024):
                    yield chunk
            finally:
                handle.close()

        return StreamingResponse(
            iterator(),
            media_type=artifact.content_type or "application/octet-stream",
            headers={"Content-Disposition": _build_content_disposition(artifact.display_name)},
        )

    return app
