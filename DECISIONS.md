# Sprint 3 decisions

- SHA-256 chosen as the storage key for deterministic content addressing and duplicate detection.

- Streaming file copy and hashing used to support large files without loading them fully into RAM.

- Two-level directory structure based on the first four hash characters chosen to avoid overly large flat directories.

- `StorageReference` returned with provider `filesystem` and a relative locator rooted under `storage/`.

- First stored file instance is preserved for duplicate content, and subsequent duplicates reuse the existing `StorageReference`.
