"""Application service for importing email messages."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
import re

from aioffice.application import (
    ArtifactLocatorConflictError,
    ArtifactRecord,
    CaseNumberProvider,
    CaseRepository,
    ImportedMailConflictError,
    ImportedMailRepository,
    MailContentParser,
    MailboxClient,
    MailImportResult,
    ParsedAttachment,
    ensure_unique_display_name,
    sanitize_display_name,
)
from aioffice.application.cases import CaseFactory
from aioffice.application.storage import DocumentStorage
from aioffice.domain import Artifact, ArtifactType, StorageReference

logger = logging.getLogger(__name__)
_CONTROL_CHARACTERS_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(slots=True)
class MailImportService:
    """Import mailbox messages into cases."""

    mailbox_client: MailboxClient
    imported_mail_repository: ImportedMailRepository
    storage: DocumentStorage
    case_factory: CaseFactory
    case_repository: CaseRepository
    case_number_provider: CaseNumberProvider
    mail_content_parser: MailContentParser
    imap_max_attachment_bytes: int = 25 * 1024 * 1024
    imap_max_attachments_per_message: int = 50

    def import_new_messages(self) -> MailImportResult:
        """Import all messages currently visible to the mailbox client."""

        imported = 0
        skipped = 0
        failed = 0

        for message in self.mailbox_client.list_messages():
            if self.imported_mail_repository.has_imported(message.mailbox_identity, message.uid):
                skipped += 1
                continue

            temporary_path: Path | None = None
            try:
                with NamedTemporaryFile(suffix=".eml", delete=False) as temporary_file:
                    temporary_file.write(message.raw_message)
                    temporary_path = Path(temporary_file.name)

                storage_reference = self.storage.store_file(temporary_path)
                existing_case = self.case_repository.get_by_artifact_locator(storage_reference.locator)
                if existing_case is not None:
                    case = existing_case.case
                else:
                    artifact = Artifact(
                        artifact_type=ArtifactType.EMAIL,
                        storage_reference=storage_reference,
                    )
                    case = self.case_factory.create_from_artifact(artifact)
                    parsed_content = self.mail_content_parser.parse(message.raw_message)
                    self._validate_attachments(parsed_content.attachments)
                    artifact_records = [
                        ArtifactRecord(
                            artifact=artifact,
                            display_name="message.eml",
                            content_type="message/rfc822",
                        )
                    ]
                    if parsed_content.body_text is not None:
                        text_artifact = Artifact(
                            artifact_type=ArtifactType.TEXT,
                            storage_reference=self._store_text_body(parsed_content.body_text),
                        )
                        case.add_artifact(text_artifact)
                        artifact_records.append(
                            ArtifactRecord(
                                artifact=text_artifact,
                                display_name="message.txt",
                                content_type="text/plain; charset=utf-8",
                            )
                        )
                    used_attachment_names: set[str] = set()
                    for index, attachment in enumerate(parsed_content.attachments, start=1):
                        display_name = self._attachment_display_name(index, attachment.filename, used_attachment_names)
                        attachment_artifact = Artifact(
                            artifact_type=ArtifactType.ATTACHMENT,
                            storage_reference=self._store_attachment(display_name, attachment),
                        )
                        case.add_artifact(attachment_artifact)
                        artifact_records.append(
                            ArtifactRecord(
                                artifact=attachment_artifact,
                                display_name=display_name,
                                content_type=attachment.content_type,
                            )
                        )
                    reference_number = self.case_number_provider.next_number()
                    try:
                        self.case_repository.save(
                            case,
                            reference_number,
                            artifact_records=tuple(artifact_records),
                        )
                    except ArtifactLocatorConflictError:
                        existing_case = self.case_repository.get_by_artifact_locator(storage_reference.locator)
                        if existing_case is None:
                            raise
                        case = existing_case.case

                self.imported_mail_repository.save_import(
                    mailbox_identity=message.mailbox_identity,
                    uid=message.uid,
                    message_id=message.message_id,
                    case_id=case.id,
                )
                imported += 1
            except ImportedMailConflictError:
                skipped += 1
            except Exception:
                failed += 1
                logger.exception(
                    "Failed to import mail message uid=%s mailbox=%s",
                    message.uid,
                    message.mailbox_identity,
                )
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()

        return MailImportResult(imported=imported, skipped=skipped, failed=failed)

    def _store_text_body(self, body_text: str) -> StorageReference:
        with NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8", newline="\n") as file:
            temporary_path = Path(file.name)
            file.write(body_text)
        try:
            return self.storage.store_file(temporary_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _store_attachment(self, display_name: str, attachment: ParsedAttachment) -> StorageReference:
        suffix = self._attachment_suffix(display_name)
        with NamedTemporaryFile(suffix=suffix, delete=False) as file:
            temporary_path = Path(file.name)
            file.write(attachment.payload)
        try:
            return self.storage.store_file(temporary_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _validate_attachments(self, attachments: tuple[ParsedAttachment, ...]) -> None:
        if len(attachments) > self.imap_max_attachments_per_message:
            msg = "mail message exceeds attachment count limit"
            raise RuntimeError(msg)
        for attachment in attachments:
            if len(attachment.payload) > self.imap_max_attachment_bytes:
                msg = "mail message exceeds attachment size limit"
                raise RuntimeError(msg)

    def _attachment_display_name(
        self,
        index: int,
        filename: str | None,
        used_names: set[str],
    ) -> str:
        fallback = f"attachment-{index:03d}.bin"
        sanitized_name = sanitize_display_name(filename, fallback=fallback)
        return ensure_unique_display_name(sanitized_name, existing_names=used_names)

    def _attachment_suffix(self, display_name: str) -> str:
        suffix = Path(display_name).suffix.lower()
        if not suffix or suffix in {".", ".."}:
            return ".bin"
        return suffix
