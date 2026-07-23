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

## Manual document text extraction

Case Workspace can now run manual text extraction for stored documents:

- PDF files with an existing text layer are supported,
- DOCX files are supported,
- OCR is not performed,
- each extracted result is stored as a separate `TEXT` artifact,
- rerunning extraction is idempotent per source artifact position,
- extraction is limited by input size and output text length.

Runtime limits:

- `AIOFFICE_DOCUMENT_EXTRACTION_MAX_INPUT_BYTES` defaults to `52428800` bytes,
- `AIOFFICE_DOCUMENT_EXTRACTION_MAX_OUTPUT_CHARS` defaults to `2000000` characters.

Notes:

- scanned PDFs without a text layer are skipped,
- `.doc` is not supported,
- extracted text can be truncated to the configured output limit,
- extraction is started manually from Case Workspace,
- generated text is linked to its source artifact by position.

## Manual AI case classification

Case Workspace can now run a manual local AI classification for one case at a time.

Enable it with:

```bash
export AIOFFICE_AI_CLASSIFICATION_ENABLED=true
export AIOFFICE_OLLAMA_BASE_URL=http://127.0.0.1:11434
export AIOFFICE_OLLAMA_MODEL=qwen2.5:7b
export AIOFFICE_OLLAMA_TIMEOUT_SECONDS=120
export AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS=100000
```

AI Office expects a local Ollama instance and a pulled model, for example:

```bash
ollama pull qwen2.5:7b
```

Notes:

- classification is disabled by default,
- classification is triggered manually from Case Workspace,
- only `TEXT` artifacts are used as input,
- supported categories are `general`, `invoice`, `complaint`, `request`, `contract`, `official_letter`, `technical_support`, and `other`,
- multiple `TEXT` artifacts are combined in artifact order with technical separators based on `display_name`,
- input text can be truncated to `AIOFFICE_AI_CLASSIFICATION_MAX_INPUT_CHARS`,
- rerunning classification replaces the current result,
- the model can be wrong and the result should be verified by the user,
- the classification result does not trigger any automatic action.
