from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, Lock

from aioffice.application import MailImportResult
from aioffice.infrastructure import MailImportPoller


def wait_until(predicate: Callable[[], bool], timeout: float = 1.0, interval: float = 0.01) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    msg = "Condition was not met before timeout"
    raise AssertionError(msg)


@dataclass(slots=True)
class _FakeMailImportService:
    outcomes: list[MailImportResult | Exception] = field(
        default_factory=lambda: [MailImportResult(imported=1, skipped=0, failed=0)]
    )
    calls: int = 0
    called_event: Event = field(default_factory=Event)
    on_call: Callable[[], None] | None = None

    def import_new_messages(self) -> MailImportResult:
        self.calls += 1
        self.called_event.set()
        if self.on_call is not None:
            self.on_call()
        outcome = self.outcomes[0] if len(self.outcomes) == 1 else self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_start_runs_poller_once() -> None:
    service = _FakeMailImportService()
    poller = MailImportPoller(
        import_service=service,
        import_lock=Lock(),
        interval_seconds=0.05,
        run_immediately=True,
    )

    poller.start()
    wait_until(lambda: poller.is_running)
    poller.stop()

    assert poller.is_running is False


def test_multiple_start_calls_do_not_create_multiple_threads() -> None:
    service = _FakeMailImportService()
    poller = MailImportPoller(service, Lock(), 0.05, run_immediately=True)

    poller.start()
    wait_until(lambda: poller.is_running)
    first_thread = poller._thread
    poller.start()
    second_thread = poller._thread
    poller.stop()

    assert first_thread is second_thread


def test_multiple_stop_calls_are_safe() -> None:
    service = _FakeMailImportService()
    poller = MailImportPoller(service, Lock(), 0.05, run_immediately=True)

    poller.start()
    wait_until(lambda: poller.is_running)
    poller.stop()
    poller.stop()

    assert poller.is_running is False


def test_run_immediately_true_calls_import_without_waiting() -> None:
    service = _FakeMailImportService()
    poller = MailImportPoller(service, Lock(), 1.0, run_immediately=True)

    poller.start()
    assert service.called_event.wait(0.2) is True
    poller.stop()

    assert service.calls >= 1


def test_run_immediately_false_waits_for_first_interval() -> None:
    service = _FakeMailImportService()
    poller = MailImportPoller(service, Lock(), 0.1, run_immediately=False)

    poller.start()
    assert service.called_event.wait(0.03) is False
    poller.stop()


def test_poller_runs_cyclically() -> None:
    service = _FakeMailImportService()
    poller = MailImportPoller(service, Lock(), 0.03, run_immediately=True)

    poller.start()
    wait_until(lambda: service.calls >= 2)
    poller.stop()

    assert service.calls >= 2


def test_exception_does_not_stop_poller_and_next_cycle_runs() -> None:
    service = _FakeMailImportService(
        outcomes=[
            RuntimeError("first cycle failed"),
            MailImportResult(imported=2, skipped=1, failed=0),
        ]
    )
    poller = MailImportPoller(service, Lock(), 0.03, run_immediately=True)

    poller.start()
    wait_until(lambda: service.calls >= 2)
    poller.stop()

    assert service.calls >= 2
    assert poller.get_status().last_result == MailImportResult(imported=2, skipped=1, failed=0)


def test_busy_lock_skips_cycle_without_error() -> None:
    service = _FakeMailImportService()
    import_lock = Lock()
    acquired = import_lock.acquire(blocking=False)
    assert acquired is True
    poller = MailImportPoller(service, import_lock, 0.03, run_immediately=True)

    poller.start()
    assert service.called_event.wait(0.08) is False
    assert poller.get_status().last_error is None
    import_lock.release()
    wait_until(lambda: service.calls >= 1)
    poller.stop()


def test_lock_is_released_after_success() -> None:
    service = _FakeMailImportService()
    import_lock = Lock()
    poller = MailImportPoller(service, import_lock, 0.03, run_immediately=True)

    poller.start()
    wait_until(lambda: service.calls >= 1)
    reacquired = import_lock.acquire(blocking=False)
    poller.stop()
    assert reacquired is True
    import_lock.release()


def test_lock_is_released_after_exception() -> None:
    service = _FakeMailImportService(outcomes=[RuntimeError("boom")])
    import_lock = Lock()
    poller = MailImportPoller(service, import_lock, 0.03, run_immediately=True)

    poller.start()
    wait_until(lambda: service.calls >= 1)
    reacquired = import_lock.acquire(blocking=False)
    poller.stop()
    assert reacquired is True
    import_lock.release()


def test_status_tracks_timestamps_and_result() -> None:
    service = _FakeMailImportService(outcomes=[MailImportResult(imported=2, skipped=3, failed=4)])
    poller = MailImportPoller(service, Lock(), 0.03, run_immediately=True)

    poller.start()
    wait_until(lambda: service.calls >= 1)
    poller.stop()
    status = poller.get_status()

    assert status.last_started_at is not None
    assert status.last_finished_at is not None
    assert status.last_success_at is not None
    assert status.last_result == MailImportResult(imported=2, skipped=3, failed=4)


def test_status_tracks_generic_error_without_raw_exception_text() -> None:
    service = _FakeMailImportService(outcomes=[RuntimeError("secret mailbox credentials")])
    poller = MailImportPoller(service, Lock(), 0.03, run_immediately=True)

    poller.start()
    wait_until(lambda: service.calls >= 1)
    poller.stop()
    status = poller.get_status()

    assert status.last_error == "IMAP import failed"
    assert status.last_finished_at is not None
    assert status.last_result is None
    assert "secret" not in status.last_error


def test_stop_returns_quickly_while_waiting_for_next_cycle() -> None:
    service = _FakeMailImportService()
    poller = MailImportPoller(service, Lock(), 10.0, run_immediately=False)

    poller.start()
    started_at = time.monotonic()
    poller.stop()
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.5


def test_poller_thread_is_daemon() -> None:
    service = _FakeMailImportService()
    poller = MailImportPoller(service, Lock(), 0.05, run_immediately=True)

    poller.start()
    wait_until(lambda: poller._thread is not None)
    thread = poller._thread
    poller.stop()

    assert thread is not None
    assert thread.daemon is True
