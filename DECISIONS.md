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

# Manual AI reply draft decisions

- One case has one current reply draft in MVP.

- Reply draft generation is always a manual human-reviewed step.

- Manual edits do not create history yet; they replace the current draft and set status to `edited`.

- Regeneration replaces the current draft and keeps the original creation timestamp.

- Ollama remains an Infrastructure adapter and Application owns the generation rules.

- Approval applies only to the current persisted draft version.

- Any content change invalidates approval immediately.

- Approval history is out of scope for MVP.

- The approver identity is declarative until authentication exists.

- `approved` does not trigger email sending or any other automatic action.
