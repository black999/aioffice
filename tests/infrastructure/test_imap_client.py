from __future__ import annotations

from email.message import EmailMessage

import pytest

from aioffice.infrastructure.imap_client import IMAPMailboxClient


class _FakeIMAPConnection:
    def __init__(self, fetch_map: dict[str, bytes], fail_fetch_uid: str | None = None) -> None:
        self.fetch_map = fetch_map
        self.fail_fetch_uid = fail_fetch_uid
        self.calls: list[tuple[object, ...]] = []
        self.logged_out = False

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        self.calls.append(("login", username, password))
        return "OK", [b"Logged in"]

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b"1"]

    def uid(self, command: str, *args: object) -> tuple[str, list[object]]:
        self.calls.append(("uid", command, *args))
        if command == "SEARCH":
            return "OK", [b"1 2"]
        if command == "FETCH":
            uid = str(args[0])
            if self.fail_fetch_uid == uid:
                return "NO", [b"failed"]
            return "OK", [(b"RFC822", self.fetch_map[uid])]
        msg = f"unexpected uid command: {command}"
        raise AssertionError(msg)

    def logout(self) -> tuple[str, list[bytes]]:
        self.logged_out = True
        self.calls.append(("logout",))
        return "BYE", [b"logout"]


def _message_bytes(subject: str, message_id: str, sender: str = "sender@example.com") -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message["From"] = sender
    message["Date"] = "Thu, 23 Jul 2026 12:00:00 +0000"
    message.set_content("hello")
    return message.as_bytes()


def test_imap_client_logs_in_selects_mailbox_and_fetches_by_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeIMAPConnection(
        fetch_map={
            "1": _message_bytes("One", "<one@example.com>"),
            "2": _message_bytes("Two", "<two@example.com>"),
        }
    )

    def imap4_ssl(host: str, port: int) -> _FakeIMAPConnection:
        assert host == "imap.example.com"
        assert port == 993
        return connection

    monkeypatch.setattr("aioffice.infrastructure.imap_client.imaplib.IMAP4_SSL", imap4_ssl)

    client = IMAPMailboxClient(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        mailbox="INBOX",
        use_ssl=True,
    )

    messages = client.list_messages()

    assert len(messages) == 2
    assert messages[0].uid == "1"
    assert messages[0].message_id == "<one@example.com>"
    assert messages[0].subject == "One"
    assert messages[0].sender == "sender@example.com"
    assert messages[0].received_at is not None
    assert messages[0].mailbox_identity == "imap.example.com/user@example.com/INBOX"
    assert ("login", "user@example.com", "secret") in connection.calls
    assert ("select", "INBOX", True) in connection.calls
    assert ("uid", "SEARCH", "ALL") in connection.calls
    assert ("uid", "FETCH", "1", "(RFC822)") in connection.calls
    assert ("uid", "FETCH", "2", "(RFC822)") in connection.calls
    assert not any(call[0] == "store" for call in connection.calls)
    assert connection.logged_out is True


def test_imap_client_logs_out_when_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeIMAPConnection(
        fetch_map={
            "1": _message_bytes("One", "<one@example.com>"),
            "2": _message_bytes("Two", "<two@example.com>"),
        },
        fail_fetch_uid="2",
    )

    monkeypatch.setattr(
        "aioffice.infrastructure.imap_client.imaplib.IMAP4_SSL",
        lambda host, port: connection,
    )

    client = IMAPMailboxClient(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        mailbox="INBOX",
        use_ssl=True,
    )

    with pytest.raises(RuntimeError, match="IMAP UID FETCH failed for UID 2"):
        client.list_messages()

    assert connection.logged_out is True


def test_imap_client_supports_non_ssl_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeIMAPConnection(
        fetch_map={
            "1": _message_bytes("One", "<one@example.com>"),
            "2": _message_bytes("Two", "<two@example.com>"),
        }
    )

    monkeypatch.setattr(
        "aioffice.infrastructure.imap_client.imaplib.IMAP4",
        lambda host, port: connection,
    )

    client = IMAPMailboxClient(
        host="imap.example.com",
        port=143,
        username="user@example.com",
        password="secret",
        mailbox="INBOX",
        use_ssl=False,
    )

    messages = client.list_messages()

    assert len(messages) == 2
    assert connection.logged_out is True
