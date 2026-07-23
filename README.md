# AI Office

See `docs/PROJECT.md` first.

## Runtime configuration

AI Office reads runtime settings from environment variables:

- `AIOFFICE_DATA_DIR`
- `AIOFFICE_HOST`
- `AIOFFICE_PORT`

Defaults:

- `AIOFFICE_DATA_DIR=storage`
- `AIOFFICE_HOST=127.0.0.1`
- `AIOFFICE_PORT=8000`

Data layout under `AIOFFICE_DATA_DIR`:

```text
AIOFFICE_DATA_DIR/
|- aioffice.db
|- artifacts/
|- incoming/
|- processed/
`- .staging/
```

Example on Ubuntu:

```bash
export AIOFFICE_DATA_DIR=/home/irek/aioffice-data
export AIOFFICE_HOST=0.0.0.0
export AIOFFICE_PORT=8000

uv run aioffice
```

## Automatic import

1. Start the application.
2. The application scans PDF files already present in `AIOFFICE_DATA_DIR/incoming`.
3. New PDF files are detected by the filesystem observer.
4. Successfully imported files are moved to `AIOFFICE_DATA_DIR/processed`.
5. Files that fail during import remain in `AIOFFICE_DATA_DIR/incoming`.

AI Office deduplicates imported documents by file content.
Importing identical PDF content again does not create another case.
The original filename does not affect deduplication.

Example on Ubuntu:

```bash
export AIOFFICE_DATA_DIR=/home/irek/aioffice-data
export AIOFFICE_HOST=0.0.0.0
export AIOFFICE_PORT=8000

uv run aioffice
```

In another terminal:

```bash
cp przykladowy.pdf /home/irek/aioffice-data/incoming/
```

## IMAP configuration

```bash
export AIOFFICE_IMAP_HOST=imap.example.com
export AIOFFICE_IMAP_PORT=993
export AIOFFICE_IMAP_USERNAME=user@example.com
export AIOFFICE_IMAP_PASSWORD='secret'
export AIOFFICE_IMAP_MAILBOX=INBOX
export AIOFFICE_IMAP_USE_SSL=true
export AIOFFICE_IMAP_POLLING_ENABLED=true
export AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS=300
export AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY=false
export AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES=26214400
export AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE=50
```

Use a proper secret store for the IMAP password in production. Environment variables are only a temporary MVP mechanism.

## Manual IMAP import

1. Configure the IMAP environment variables.
2. Start the application with `uv run aioffice`.
3. Open the dashboard in your browser.
4. Click `Importuj pocztę`.

The IMAP import is currently manual and synchronous. The HTTP request stays open until the import finishes.

## Automatic IMAP polling

Set the polling variables to enable automatic mailbox checks:

- `AIOFFICE_IMAP_POLLING_ENABLED=true`
- `AIOFFICE_IMAP_POLLING_INTERVAL_SECONDS=300`
- `AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY=false`

Notes:

- Polling is disabled by default.
- The default interval is 300 seconds.
- The minimum interval is 30 seconds.
- `AIOFFICE_IMAP_POLLING_RUN_IMMEDIATELY=true` starts the first import cycle right after the poller thread starts.
- The manual `Importuj pocztę` button still works.
- The import lock protects only one application process instance.
- Poll status is kept only in process memory and is lost after restart.

## Mail artifacts

For each imported email message:

- the full message is stored as a primary `.eml` artifact,
- the extracted body is stored as a UTF-8 `.txt` artifact when useful text exists,
- attachments are stored as separate attachment artifacts.

Attachment safety limits:

- `AIOFFICE_IMAP_MAX_ATTACHMENT_BYTES` defaults to `26214400` bytes (25 MiB),
- `AIOFFICE_IMAP_MAX_ATTACHMENTS_PER_MESSAGE` defaults to `50`,
- attachment size must stay between `1048576` and `104857600` bytes,
- attachment count must stay between `1` and `200`.

Attachments are not yet analyzed by AI or OCR.

## Case Workspace

The Case Workspace now shows:

- the business case reference,
- the extracted plain-text email body when a `TEXT` artifact exists,
- the ordered list of stored artifacts with safe display names,
- a download link for each artifact.

Artifact downloads use the case UUID and artifact position:

- `GET /cases/{case_id}/artifacts/{position}/download`

The storage locator is not exposed as a request parameter.
Email HTML is displayed as escaped plain text.

Still out of scope:

- PDF preview,
- inline attachment rendering,
- OCR.
