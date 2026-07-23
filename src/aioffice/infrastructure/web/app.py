"""FastAPI application bootstrap."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import Iterator
from pathlib import Path
from threading import Lock
from typing import AsyncIterator
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates

from aioffice.application import CaseFactory, MailImportResult, sanitize_display_name
from aioffice.application.services import (
    ArtifactDownloadService,
    CaseDashboardService,
    CaseWorkspaceService,
    DocumentImportService,
    MailImportService,
)
from aioffice.application.storage import ArtifactNotFoundError, UnsupportedStorageError
from aioffice.infrastructure import (
    AppSettings,
    FilesystemStorage,
    IMAPMailboxClient,
    MailImportPoller,
    MailPollStatus,
    SQLiteCaseNumberProvider,
    SQLiteCaseRepository,
    SQLiteImportedMailRepository,
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


def _build_mail_polling_snapshot(
    poller: MailImportPoller | None,
) -> tuple[bool, int | None, MailPollStatus | None]:
    if poller is None:
        return False, None, None
    return True, int(poller.interval_seconds), poller.get_status()


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
    dashboard_service = CaseDashboardService(repository=repository)

    import_repository = SQLiteCaseRepository(database_path=settings.database_path)
    number_provider = SQLiteCaseNumberProvider(database_path=settings.database_path)
    storage = FilesystemStorage(root_directory=settings.data_directory)
    workspace_service = CaseWorkspaceService(repository=repository, storage_reader=storage)
    download_service = ArtifactDownloadService(repository=repository, storage_reader=storage)
    import_service = DocumentImportService(
        storage=storage,
        case_factory=CaseFactory(),
        case_repository=import_repository,
        case_number_provider=number_provider,
    )
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
            repository.close()
            import_repository.close()
            number_provider.close()

    app = FastAPI(title="AI Office", lifespan=lifespan)
    app.state.mail_import_service = mail_import_service
    app.state.mail_import_lock = mail_import_lock
    app.state.mail_import_poller = mail_import_poller

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
        workspace = workspace_service.get_case_workspace(case_id)
        if workspace is None:
            raise HTTPException(status_code=404)
        return _TEMPLATES.TemplateResponse(
            request,
            "case_workspace.html",
            {
                "page_title": workspace.case_reference,
                "workspace": workspace,
            },
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
