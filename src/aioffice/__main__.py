"""Application entrypoint for running the AI Office web bootstrap."""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Run the AI Office web application."""

    uvicorn.run("aioffice.infrastructure.web.app:create_app", factory=True, host="127.0.0.1", port=8000)
