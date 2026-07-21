# Review

## Things noticed

- Current `FilesystemStorage` implementation keeps the storage root convention inside infrastructure code. If more storage backends appear later, a shared application-level contract may become useful.

- Duplicate detection currently treats content hash as the source of truth and keeps the first stored extension. This is simple and deterministic for Sprint 3, but it may require an explicit product decision later if filename metadata becomes important.

No architectural change proposed.
