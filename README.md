# AI Office

See docs/PROJECT.md first.

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
├── aioffice.db
├── artifacts/
├── incoming/
└── .staging/
```

Example on Ubuntu:

```bash
export AIOFFICE_DATA_DIR=/home/irek/aioffice-data
export AIOFFICE_HOST=0.0.0.0
export AIOFFICE_PORT=8000

uv run aioffice
```
