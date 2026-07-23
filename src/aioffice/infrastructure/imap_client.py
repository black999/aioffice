"""IMAP client implementation using the Python standard library."""

from __future__ import annotations

import imaplib
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from email.policy import default
from email.utils import parsedate_to_datetime

from aioffice.application import MailboxClient, MailboxMessage


@dataclass(slots=True)
class IMAPMailboxClient(MailboxClient):
    """List messages from a single IMAP mailbox."""

    host: str
    port: int
    username: str
    password: str
    mailbox: str = "INBOX"
    use_ssl: bool = True

    def list_messages(self) -> tuple[MailboxMessage, ...]:
        """Return messages from the configured mailbox using IMAP UID."""

        connection: imaplib.IMAP4 | None = None
        try:
            if self.use_ssl:
                connection = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                connection = imaplib.IMAP4(self.host, self.port)
            connection.login(self.username, self.password)
            connection.select(self.mailbox, readonly=True)
            status, search_data = connection.uid("SEARCH", "ALL")
            if status != "OK":
                msg = "IMAP UID SEARCH failed"
                raise RuntimeError(msg)
            uid_values = tuple(uid.decode("utf-8") for uid in search_data[0].split() if uid)
            mailbox_identity = f"{self.host}/{self.username}/{self.mailbox}"
            return tuple(
                self._fetch_message(connection, mailbox_identity, uid)
                for uid in uid_values
            )
        finally:
            if connection is not None:
                connection.logout()

    def _fetch_message(
        self,
        connection: imaplib.IMAP4,
        mailbox_identity: str,
        uid: str,
    ) -> MailboxMessage:
        status, fetch_data = connection.uid("FETCH", uid, "(RFC822)")
        if status != "OK":
            msg = f"IMAP UID FETCH failed for UID {uid}"
            raise RuntimeError(msg)
        raw_message = self._extract_raw_message(fetch_data)
        parsed_message = message_from_bytes(raw_message, policy=default)
        return MailboxMessage(
            mailbox_identity=mailbox_identity,
            uid=uid,
            message_id=parsed_message.get("Message-ID"),
            subject=parsed_message.get("Subject"),
            sender=parsed_message.get("From"),
            received_at=self._parse_received_at(parsed_message.get("Date")),
            raw_message=raw_message,
        )

    def _extract_raw_message(self, fetch_data: list[object]) -> bytes:
        for item in fetch_data:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], bytes):
                return item[1]
        msg = "IMAP FETCH response does not contain RFC822 message bytes"
        raise RuntimeError(msg)

    def _parse_received_at(self, date_header: str | None) -> datetime | None:
        if date_header is None:
            return None
        try:
            return parsedate_to_datetime(date_header)
        except (TypeError, ValueError, IndexError):
            return None
