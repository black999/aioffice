"""Watch-folder integration for importing PDF documents."""

from __future__ import annotations

import logging
import shutil
from contextlib import suppress
from dataclasses import dataclass, field
from os import fsdecode
from pathlib import Path

from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from aioffice.application.services import DocumentImportService
from aioffice.domain import Case

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WatchFolder:
    """Monitor a directory and import newly created PDF documents."""

    watch_directory: Path
    processed_directory: Path
    import_service: DocumentImportService
    _observer: BaseObserver = field(init=False, repr=False)
    _event_handler: _WatchFolderEventHandler = field(init=False, repr=False)
    _started: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        self.watch_directory = self.watch_directory.expanduser().resolve()
        self.processed_directory = self.processed_directory.expanduser().resolve()
        self._observer = Observer()
        self._event_handler = _WatchFolderEventHandler(self)

    def start(self) -> None:
        """Start monitoring the configured directory."""

        if self._started:
            return
        self.watch_directory.mkdir(parents=True, exist_ok=True)
        self.processed_directory.mkdir(parents=True, exist_ok=True)
        self._observer.schedule(self._event_handler, str(self.watch_directory), recursive=False)
        self._observer.start()
        self._started = True
        self._process_existing_files()

    def stop(self) -> None:
        """Stop monitoring the configured directory."""

        if not self._started:
            return
        self._observer.stop()
        with suppress(RuntimeError):
            if self._observer.is_alive():
                self._observer.join()
        self._started = False

    def process_path(self, file_path: Path) -> Case | None:
        """Import a newly created PDF file if it is supported."""

        normalized_path = file_path.expanduser().resolve()
        if not normalized_path.is_file():
            return None
        if self._is_ignored(normalized_path):
            return None

        case = self.import_service.import_pdf(normalized_path)
        self._move_to_processed(normalized_path)
        return case

    def _is_ignored(self, file_path: Path) -> bool:
        return (
            file_path.suffix.lower() != ".pdf"
            or file_path.name.startswith("~$")
            or file_path.name.startswith(".")
            or file_path.name.endswith(".tmp")
            or file_path.name.endswith(".part")
            or file_path.name.endswith(".partial")
        )

    def _process_existing_files(self) -> None:
        for file_path in sorted(self.watch_directory.iterdir()):
            if not file_path.is_file():
                continue
            try:
                self.process_path(file_path)
            except Exception:
                logger.exception("Failed to import existing document: %s", file_path)

    def _move_to_processed(self, source_path: Path) -> None:
        self.processed_directory.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(self._next_processed_path(source_path)))

    def _next_processed_path(self, source_path: Path) -> Path:
        candidate = self.processed_directory / source_path.name
        if not candidate.exists():
            return candidate

        suffix = source_path.suffix
        stem = source_path.stem
        index = 1
        while True:
            candidate = self.processed_directory / f"{stem}-{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1


@dataclass(slots=True, eq=False)
class _WatchFolderEventHandler(FileSystemEventHandler):
    """Bridge filesystem events to the watch-folder service."""

    watch_folder: WatchFolder

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        """Handle newly created filesystem entries."""

        if event.is_directory:
            return
        file_path = Path(fsdecode(event.src_path))
        try:
            self.watch_folder.process_path(file_path)
        except Exception:
            logger.exception("Failed to import document: %s", file_path)

    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        """Handle modified filesystem entries."""

        if event.is_directory:
            return
        file_path = Path(fsdecode(event.src_path))
        try:
            self.watch_folder.process_path(file_path)
        except Exception:
            logger.exception("Failed to import document: %s", file_path)
