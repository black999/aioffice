# Review

## Things noticed

- `SQLiteCaseRepository` currently reconstructs `Case` with only its identifier because artifact persistence is explicitly out of scope. This keeps the persistence step small, but it means a reloaded case is not yet a full aggregate.

- `status` and `created_at` are stored in SQLite as repository-owned metadata because the current `Case` domain model does not expose those fields. This is acceptable for the current issue, but those fields should eventually become an explicit application or domain decision.

## Architect feedback

- `SQLiteCaseRepository` currently rebuilds entities with `Case(id=Identifier.from_string(...))`. This is acceptable for now, but a future refactor should consider a dedicated rehydration path such as `Case.restore(...)` or `Case.rehydrate(...)`.

- `default_status = "open"` is accepted temporarily, but it should be treated as technical debt because the repository is currently defining a business-level default value.

- `close()` is sufficient for now, but repository lifecycle would be cleaner in the future with context manager support, for example `with SQLiteCaseRepository(...) as repo:`.

## Web bootstrap

- The web layer currently creates and closes `SQLiteCaseRepository` per request. This is acceptable for a single read-only page, but a later stage should centralize dependency wiring and repository lifecycle.

- `CaseDashboardService` currently supplies a default `"open"` status because status is not yet exposed as a real read model from persistence. That keeps the page minimal, but it should be replaced once case status becomes explicit in the application model.

## Case reference number

- `SQLiteCaseRepository` now persists `reference_number`, but the allocation logic is intentionally separate in `SQLiteCaseNumberProvider`. This keeps business numbering out of the repository, at the cost of coordinating two infrastructure components during document import.

- Artifact persistence is still partial. The repository stores only a primary artifact locator so the dashboard and duplicate detection can survive restart, but full artifact persistence is still deferred.

## Filesystem storage layout

- `FilesystemStorage` now treats `root_directory` as the direct application data directory. Existing developer data under `data_directory/storage/artifacts/` would require a manual move to `data_directory/artifacts/` after this change.

## WatchFolder runtime

- There is no `failed/` directory yet.
- There is no retry mechanism yet.
- A move failure after a successful import can leave a saved case in SQLite while the source file remains in `incoming`.
- Re-copying the same file into `incoming` can still trigger another import attempt path.
- Deduplication is based on the full SHA-256 of file content.
- Changing even a single byte creates a new document.
- There is no manual workflow yet for merging already duplicated cases.
- Files in `processed` are not cleaned up automatically.
- Dashboard updates still require a manual refresh.

## IMAP import

- IMAP import can now be started manually from the dashboard.
- Automatic IMAP polling is now available inside the application process.
- Poller status is not persisted and is lost after restart.
- The HTTP request remains open until a manual IMAP import finishes.
- The import lock protects only a single application process instance.
- Multiple workers can still run separate imports because there is no distributed lock.
- There is no distributed lock across multiple processes or hosts.
- There are no per-account schedules yet.
- There is no OCR yet.
- There is no text extraction from PDF or DOCX yet.
- The UI does not allow downloading artifacts yet.
- There is no antivirus scanning for attachments yet.
- There is no garbage collector for unreferenced content-addressed files yet.
- Attachment filenames are sanitized before storage-derived suffix selection.
- Case status still does not depend on parsing outcomes.
- OAuth2 is not supported yet.
- Multiple accounts are not supported yet.
- Automatic replies are not implemented.
- Imported messages are not moved to another folder after import.
- The IMAP password is currently passed through an environment variable.

## Artifact downloads

- Case Workspace now shows extracted email body text and artifact download links.
- Download endpoints currently have no authentication or per-case authorization.
- Any user with access to the application can download stored artifacts.
- Physical storage paths are not exposed through the HTTP API.
- Range requests are not supported yet.
- Browser preview for PDF or other artifacts is not implemented yet.
- Antivirus scanning is not implemented yet.
- OCR is not implemented yet.
- Retention rules and garbage collection for unreferenced artifacts are not implemented yet.

## Document extraction

- PDF extraction currently works only for PDFs that already contain a text layer.
- Scanned PDFs still require future OCR.
- `.doc` is not supported.
- XLSX, ODT, and RTF are not supported.
- Extraction is manual from Case Workspace and is not triggered automatically after import.
- There is still no full-text index.
- Generated text is not versioned if the source artifact changes at the same position.
- Extracted text can be truncated to the configured output limit.
- A failed repository save can leave an orphaned content-addressed text file in storage.

## Manual AI classification

- Classification is probabilistic and requires user verification.
- No automatic action is triggered from the assigned category.
- Only the latest classification is stored; there is no history yet.
- Prompt versions are not tracked yet.
- Model versions are only tracked by the configured model name.
- Batch classification is not implemented.
- Automatic classification after import is not implemented.
- There is no background queue; classification runs synchronously in the HTTP request.
- The only runtime bound for the model call is the HTTP timeout.
- The classification lock works only inside a single process.
- Multiple application workers could still classify different cases in parallel.
- The classification endpoint has no authentication yet.
- A local Ollama operator can access document content processed by the model.
- External Ollama endpoints should not be used for confidential data.

## Manual AI reply drafts

- Reply drafts are not sent automatically.
- There is no approval workflow yet.
- There is no version history for drafts.
- There are no signatures or company templates yet.
- There is no recipient model yet.
- Draft generation supports only Polish output in this MVP.
- There are no legal or compliance rules beyond prompt guidance.
- Generation is manual and is not triggered automatically after import or classification.
- The generation lock works only inside one process.
- There is no background queue.
- The endpoints have no authentication yet.
- The model can hallucinate and every draft requires human verification.

No architectural change proposed.
