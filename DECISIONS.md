# Persistence decisions

- `sqlite3` from the Python standard library chosen to keep persistence local, simple, and dependency-free.

- A single database file at `storage/aioffice.db` is the default persistence target for this stage.

- The first repository persists only `Case` rows, while artifact persistence remains out of scope.

- SQL is written manually with parameterized statements only; no ORM or SQLAlchemy layer was introduced.

- The `cases` table stores `id`, `status`, and `created_at` as an extendable base schema.
