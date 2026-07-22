"""Watch-folder integration for importing PDF documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from os import fsdecode
from pathlib import Path

from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from aioffice.application.services import DocumentImportService
from aioffice.domain import Case


@dataclass(slots=True)
class WatchFolder:
    """Monitor a directory and import newly created PDF documents."""

    watch_directory: Path
    import_service: DocumentImportService
    _observer: BaseObserver = field(init=False, repr=False)
    _event_handler: _WatchFolderEventHandler = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.watch_directory = self.watch_directory.expanduser().resolve()
        self._observer = Observer()
        self._event_handler = _WatchFolderEventHandler(self)

    def start(self) -> None:
        """Start monitoring the configured directory."""

        self.watch_directory.mkdir(parents=True, exist_ok=True)
        self._observer.schedule(self._event_handler, str(self.watch_directory), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        """Stop monitoring the configured directory."""

        self._observer.stop()
        self._observer.join()

    def process_path(self, file_path: Path) -> Case | None:
        """Import a newly created PDF file if it is supported."""

        normalized_path = file_path.expanduser().resolve()
        if not normalized_path.is_file():
            return None
        if self._is_ignored(normalized_path):
            return None

        return self.import_service.import_pdf(normalized_path)

    def _is_ignored(self, file_path: Path) -> bool:
        return (
            file_path.suffix.lower() != ".pdf"
            or file_path.name.startswith("~$")
            or file_path.name.startswith(".")
            or file_path.name.endswith(".tmp")
            or file_path.name.endswith(".part")
            or file_path.name.endswith(".partial")
        )


@dataclass(slots=True)
class _WatchFolderEventHandler(FileSystemEventHandler):
    """Bridge filesystem events to the watch-folder service."""

    watch_folder: WatchFolder

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        """Handle newly created filesystem entries."""

        if event.is_directory:
            return
        self.watch_folder.process_path(Path(fsdecode(event.src_path)))
