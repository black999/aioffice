"""FastAPI application bootstrap."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aioffice.application import CaseFactory, MailImportResult
from aioffice.application.services import (
    CaseDashboardService,
    CaseWorkspaceService,
    DocumentImportService,
    MailImportService,
)
from aioffice.infrastructure import (
    AppSettings,
    FilesystemStorage,
    IMAPMailboxClient,
    SQLiteCaseNumberProvider,
    SQLiteCaseRepository,
    SQLiteImportedMailRepository,
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


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create the FastAPI application."""

    if settings is None:
        settings = AppSettings.from_environment()

    repository = SQLiteCaseRepository(database_path=settings.database_path)
    dashboard_service = CaseDashboardService(repository=repository)
    workspace_service = CaseWorkspaceService(repository=repository)

    import_repository = SQLiteCaseRepository(database_path=settings.database_path)
    number_provider = SQLiteCaseNumberProvider(database_path=settings.database_path)
    storage = FilesystemStorage(root_directory=settings.data_directory)
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
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            watch_folder.start()
            yield
        finally:
            watch_folder.stop()
            repository.close()
            import_repository.close()
            number_provider.close()
            if imported_mail_repository is not None:
                imported_mail_repository.close()

    app = FastAPI(title="AI Office", lifespan=lifespan)
    app.state.mail_import_service = mail_import_service
    app.state.mail_import_lock = Lock()

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "page_title": "AI Office",
                "case_count": dashboard_service.count_cases(),
                "cases": dashboard_service.list_cases(),
                "mail_import_available": request.app.state.mail_import_service is not None,
                "mail_import_message": _build_mail_import_message(request),
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

    return app
