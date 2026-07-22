# Review

## Things noticed

- `SQLiteCaseRepository` currently reconstructs `Case` with only its identifier because artifact persistence is explicitly out of scope. This keeps the persistence step small, but it means a reloaded case is not yet a full aggregate.

- `status` and `created_at` are stored in SQLite as repository-owned metadata because the current `Case` domain model does not expose those fields. This is acceptable for the current issue, but those fields should eventually become an explicit application or domain decision.

No architectural change proposed.
