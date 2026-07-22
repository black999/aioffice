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
