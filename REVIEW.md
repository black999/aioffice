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

No architectural change proposed.
