"""Automatic IMAP polling runtime component."""

from __future__ import annotations

import logging
from _thread import LockType
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from threading import Event, RLock, Thread

from aioffice.application import MailImportResult
from aioffice.application.services import MailImportService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MailPollStatus:
    """Thread-safe snapshot of automatic IMAP polling state."""

    running: bool
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_success_at: datetime | None
    last_result: MailImportResult | None
    last_error: str | None


@dataclass(slots=True)
class MailImportPoller:
    """Periodically run the existing mail import service in a daemon thread."""

    import_service: MailImportService
    import_lock: LockType
    interval_seconds: float
    run_immediately: bool = False
    _stop_event: Event = field(init=False, repr=False)
    _status_lock: RLock = field(init=False, repr=False)
    _thread: Thread | None = field(init=False, default=None, repr=False)
    _status: MailPollStatus = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._stop_event = Event()
        self._status_lock = RLock()
        self._status = MailPollStatus(
            running=False,
            last_started_at=None,
            last_finished_at=None,
            last_success_at=None,
            last_result=None,
            last_error=None,
        )

    def start(self) -> None:
        """Start the polling thread once."""

        with self._status_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._status = replace(self._status, running=True)
            self._thread = Thread(target=self._run_loop, name="aioffice-mail-poller", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the polling thread and wait for shutdown."""

        with self._status_lock:
            thread = self._thread
            self._stop_event.set()
        if thread is not None:
            thread.join()

    @property
    def is_running(self) -> bool:
        """Return whether the poller thread is currently running."""

        with self._status_lock:
            return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> MailPollStatus:
        """Return a thread-safe snapshot of poller status."""

        with self._status_lock:
            return self._status

    def _run_loop(self) -> None:
        try:
            first_iteration = True
            while not self._stop_event.is_set():
                if first_iteration:
                    first_iteration = False
                    if not self.run_immediately and self._stop_event.wait(self.interval_seconds):
                        break
                elif self._stop_event.wait(self.interval_seconds):
                    break
                self._run_cycle()
        finally:
            with self._status_lock:
                self._status = replace(self._status, running=False)

    def _run_cycle(self) -> None:
        if not self.import_lock.acquire(blocking=False):
            logger.info("Skipping automatic IMAP import because another import is running")
            return

        started_at = datetime.now(UTC)
        with self._status_lock:
            self._status = replace(
                self._status,
                last_started_at=started_at,
                last_finished_at=None,
                last_error=None,
            )

        try:
            result = self.import_service.import_new_messages()
        except Exception:
            finished_at = datetime.now(UTC)
            logger.exception("Automatic IMAP import failed")
            with self._status_lock:
                self._status = replace(
                    self._status,
                    last_finished_at=finished_at,
                    last_error="IMAP import failed",
                    last_result=None,
                )
        else:
            finished_at = datetime.now(UTC)
            logger.info(
                "Automatic IMAP import finished: imported=%s skipped=%s failed=%s",
                result.imported,
                result.skipped,
                result.failed,
            )
            with self._status_lock:
                self._status = replace(
                    self._status,
                    last_finished_at=finished_at,
                    last_success_at=finished_at,
                    last_result=result,
                    last_error=None,
                )
        finally:
            self.import_lock.release()
