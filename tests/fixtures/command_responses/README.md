# Command Response Fixtures

These golden JSON files are executable examples for the public Spine agent command
contract response shapes. They are not a second source of authority; the
normative rules live in `specs/agent-command-contract.md`.

Fixture shape rules:

- Public version-like fields are strings: `version`, `current_version`,
  `target_version`, and list `limit`.
- Absent optional output fields are omitted instead of represented as `null`.
- `current_common`, `event_detail`, and `task_detail` are nested public objects.
- `semantic_facts_hash` is the Spine canonical JSON hash of `semantic_facts`.
