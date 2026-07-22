"""FastAPI application bootstrap."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aioffice.application.services import CaseDashboardService, CaseWorkspaceService
from aioffice.infrastructure.config import AppSettings
from aioffice.infrastructure.sqlite_repository import SQLiteCaseRepository


_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create the FastAPI application."""

    if settings is None:
        settings = AppSettings.from_environment()

    app = FastAPI(title="AI Office")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        repository = SQLiteCaseRepository(database_path=settings.database_path)
        try:
            dashboard_service = CaseDashboardService(repository=repository)
            return _TEMPLATES.TemplateResponse(
                request,
                "index.html",
                {
                    "page_title": "AI Office",
                    "case_count": dashboard_service.count_cases(),
                    "cases": dashboard_service.list_cases(),
                },
            )
        finally:
            repository.close()

    @app.get("/cases/{case_id}", response_class=HTMLResponse)
    def case_workspace(request: Request, case_id: str) -> HTMLResponse:
        repository = SQLiteCaseRepository(database_path=settings.database_path)
        try:
            workspace_service = CaseWorkspaceService(repository=repository)
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
        finally:
            repository.close()

    return app
