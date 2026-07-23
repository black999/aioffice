"""Application service for importing email messages."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from aioffice.application import (
    ArtifactLocatorConflictError,
    CaseNumberProvider,
    CaseRepository,
    ImportedMailConflictError,
    ImportedMailRepository,
    MailboxClient,
    MailImportResult,
)
from aioffice.application.cases import CaseFactory
from aioffice.application.storage import DocumentStorage
from aioffice.domain import Artifact, ArtifactType

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MailImportService:
    """Import mailbox messages into cases."""

    mailbox_client: MailboxClient
    imported_mail_repository: ImportedMailRepository
    storage: DocumentStorage
    case_factory: CaseFactory
    case_repository: CaseRepository
    case_number_provider: CaseNumberProvider

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
                    reference_number = self.case_number_provider.next_number()
                    artifact = Artifact(
                        artifact_type=ArtifactType.EMAIL,
                        storage_reference=storage_reference,
                    )
                    case = self.case_factory.create_from_artifact(artifact)
                    try:
                        self.case_repository.save(case, reference_number)
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
