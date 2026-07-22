"""Application entrypoint for running the AI Office web bootstrap."""

from __future__ import annotations

import uvicorn

from aioffice.infrastructure import AppSettings


def main() -> None:
    """Run the AI Office web application."""

    settings = AppSettings.from_environment()
    uvicorn.run(
        "aioffice.infrastructure.web.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )
