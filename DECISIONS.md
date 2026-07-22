# Case Reference Number decisions

- Business reference numbers use an integer sequence and are formatted for users as `CASE-000001`.

- UUID remains the internal technical identifier of `Case` and is not shown in the dashboard.

- Number allocation belongs to Application through `CaseNumberProvider`, while SQLite only persists the assigned number.

- Formatting stays outside persistence so presentation can evolve without schema changes.

- `DocumentImportService` is the first application entrypoint responsible for assigning a case number before persistence.
