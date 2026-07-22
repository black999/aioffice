"""FastAPI application bootstrap."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aioffice.application.services import CaseDashboardService
from aioffice.infrastructure.sqlite_repository import SQLiteCaseRepository


_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))


def create_app() -> FastAPI:
    """Create the FastAPI application."""

    app = FastAPI(title="AI Office")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        repository = SQLiteCaseRepository(database_path=Path("storage") / "aioffice.db")
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

    return app
