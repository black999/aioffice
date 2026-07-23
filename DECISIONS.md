# Case Reference Number decisions

- Business reference numbers use an integer sequence and are formatted for users as `CASE-000001`.

- UUID remains the internal technical identifier of `Case` and is not shown in the dashboard.

- Number allocation belongs to Application through `CaseNumberProvider`, while SQLite only persists the assigned number.

- Formatting stays outside persistence so presentation can evolve without schema changes.

- `DocumentImportService` is the first application entrypoint responsible for assigning a case number before persistence.

# Manual AI classification decisions

- Manual case classification is implemented in Application through `CaseClassificationService`.

- Allowed categories are fixed in code and validated before persistence.

- Only `TEXT` artifacts are sent to the local model.

- Ollama is accessed through a small Infrastructure adapter based on `urllib.request`.

- Model responses must be JSON and are validated before saving to SQLite.

- Only one current classification per case is stored; history is deferred.

- Classification is opt-in through runtime configuration and disabled by default.
