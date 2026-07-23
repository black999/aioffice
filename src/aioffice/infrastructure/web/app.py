"""FastAPI application bootstrap."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aioffice.application import CaseFactory
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

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "page_title": "AI Office",
                "case_count": dashboard_service.count_cases(),
                "cases": dashboard_service.list_cases(),
            },
        )

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
