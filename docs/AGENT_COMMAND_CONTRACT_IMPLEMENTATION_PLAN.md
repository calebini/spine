# Agent Command Contract Implementation Plan

Status: Working implementation plan  
Scope: Build sequence for completing the `specs/agent-command-contract.md` command core and CLI surface

This document is non-normative. If it conflicts with `specs/agent-command-contract.md` or the ontology, the specs win. Its job is to keep implementation moving in small executable slices while using golden fixtures to turn ambiguous contract prose into concrete behavior.

## Lighthouse

Optimize for a small deterministic command core that can be tested from golden JSON fixtures without knowing anything about the eventual CLI, MCP, HTTP, or worker runtime.

When an implementation choice is ambiguous, prefer the choice that:

- makes replay and generated identities easiest to test;
- gives agents stable public JSON rather than internal row dumps;
- keeps one canonical shape for each concept;
- omits absent optional fields instead of returning fake `null` states;
- treats `command_receipts` as the replay index;
- keeps transport behavior outside the command core.

## Track Rhythm

Each slice should follow the same loop:

1. Align the spec only enough to bless known fixture decisions.
2. Add or update golden fixtures.
3. Implement the narrowest command-core behavior that satisfies those fixtures.
4. Add ledger/CLI behavior only when the command-core contract is pinned.
5. Run focused tests.
6. Run Whetstone diagnostics only after executable examples exist.

## Slice 0: Stabilized Draft Baseline

Status: Done

Inputs:

- `specs/agent-command-contract.md` at `Draft v0.1.125`.
- Initial `src/spine/commands/` package.
- Initial golden fixtures under `tests/fixtures/command_responses/`.

Exit criteria:

- Source spec and Whetstone run draft are synchronized.
- Existing unittest suite passes.
- Command response fixture tests pass.

## Slice 1: Spec Alignment To Initial Fixtures

Purpose: Make the spec explicitly bless the choices already made by the first fixture set.

Spec alignment:

- State that public JSON version-like fields currently represented in fixtures are strings: `version`, `current_version`, `target_version`, and list `limit`.
- State that absent optional output fields are omitted.
- State that `current_common`, `event_detail`, and `task_detail` are nested public objects.
- State that `semantic_facts_hash` is computed by Spine canonical JSON hashing over `semantic_facts`.
- Add a short pointer that golden command response fixtures are executable examples, not alternate authority.

Fixtures:

- Add `tests/fixtures/command_responses/README.md`.
- Keep existing fixture names stable.

Tests:

- `PYTHONPATH=src python3 -m unittest tests.test_command_response_fixtures`
- `PYTHONPATH=src python3 -m unittest discover -s tests`

Exit criteria:

- Spec, response builders, and fixture README agree on public shape rules.
- No new runtime behavior beyond documentation/fixtures.

## Slice 2: Subject Upsert And Receipt Index

Purpose: Implement the first receipt-producing write command with minimal ledger mutation.

Implementation:

- Add `subject.upsert` to `spine.commands.handle`.
- Create or update `subjects` deterministically.
- Create a `command_receipts` row for fresh insert, changed update, no-op, and compatible replay.
- Enforce global `command_id` uniqueness through command receipt lookup.
- Return structured `semantic_conflict` on incompatible replay or cross-command `command_id` reuse.

Spec/fixture decisions:

- Pin `subject.upsert` response shape in fixtures.
- Pin `subject_created`, `subject_updated`, and `subject_noop` receipt envelopes.
- Confirm `action_timestamp_utc=updated_at_utc` for all `subject.upsert` receipt branches.

Tests:

- first-subject bootstrap success;
- fresh subject insert;
- changed update;
- no-op update;
- compatible replay;
- incompatible replay;
- cross-command `command_id` collision against a seeded receipt.

Exit criteria:

- The command receipt table exists or has a documented transitional in-memory substitute only if schema migration is intentionally deferred.
- Fixture tests prove receipt hash determinism.

## Slice 3: Real Read Commands

Purpose: Make `item.show` and `item.list` real command-core reads over the existing ledger.

Implementation:

- Tighten `item.show` handler validation and errors.
- Tighten `item.list` filters: `item_type`, `status`, `include_archived`, `limit`.
- Preserve deterministic ordering: `updated_at_utc` descending, then `item_id` ascending.
- Add nested collection limits/truncation for `item.show`.
- Add embedded temporal anchor outputs for event/task details and notification policies.

Spec/fixture decisions:

- Pin `item.show` event, task, and archived item examples.
- Pin `item.list` active/default, archived filter, item type filter, and limit zero examples.
- Decide whether `item.list` includes relation summaries in MVP; default should be no.

Tests:

- missing item failure;
- filter validation failures;
- deterministic ordering;
- optional field omission;
- embedded anchor shape.

Exit criteria:

- Read commands are usable from `spine.commands.handle`.
- No CLI dependency exists inside command core.

## Slice 4: CLI Adapter Skeleton

Purpose: Add the first `spine` CLI entry point without implementing all commands.

Implementation:

- Add a CLI module that maps command words to canonical dotted commands.
- Parse `--db`, `--input`, `--input -`, `--pretty`, and `--dry-run`.
- Normalize `CommandContext`.
- Invoke `spine.commands.handle`.
- Return exactly one JSON response to stdout.
- Map command-core errors and CLI preflight errors to normative exit codes.

Spec/fixture decisions:

- Add CLI preflight fixture examples for invalid JSON, missing DB, unavailable DB, unsupported command, and pretty whitespace.
- Decide the package script name. Prefer `spine` only if it will not collide with another local tool; otherwise use `spine-command` until the final CLI name is ratified.

Tests:

- CLI command resolution;
- `--input` file and stdin;
- pretty output only changes whitespace;
- dry-run write preflight requires readable ledger only;
- non-dry-run write preflight requires writable DB and parent directory.

Exit criteria:

- CLI can execute `item.show` and `item.list` through command core.
- Unsupported write commands fail as unsupported rather than partially implemented.

## Slice 5: Event And Task Create Commands

Purpose: Implement first item-authoring commands with receipts and fixture-backed responses.

Implementation:

- Add `event.create`.
- Add `task.create`.
- Use existing ledger creation workflows where possible.
- Add command-derived IDs for item, audit, receipt, anchors, supporting rows.
- Create command receipts for fresh create and compatible replay.
- Validate duplicate supporting sets before mutation.
- Keep reminder work generation out of create commands; initial notification policies are inert.

Spec/fixture decisions:

- Pin event create fixture with start anchor.
- Pin task create fixture without due anchor.
- Pin create-with-supporting-sets fixture after the basic create path is stable.
- Pin duplicate-supporting-set failure fixtures.

Tests:

- successful event/task create;
- compatible replay;
- incompatible replay;
- missing actor;
- invalid anchor shape;
- duplicate locations/roles/notification policies;
- no partial mutation on failure.

Exit criteria:

- Agents can create and inspect simple events/tasks through command core and CLI.

## Slice 6: Common Patch And No-Op Updates

Purpose: Implement update semantics for common item fields before broader lifecycle work.

Implementation:

- Add shared patch normalizer for `title`, `summary`, and `source_ref`.
- Add `event.update`.
- Add `task.update`.
- Support fresh change, no-op, compatible replay, incompatible replay.
- Create receipts for all successful branches.
- Reject wrong item type, stale target version, archived target, invalid patch, and unsupported patch keys.

Spec/fixture decisions:

- Pin fresh/no-op/replay fixtures for `event.update` and `task.update`.
- Pin invalid patch failure fixtures.
- Confirm omitted optional fields vs cleared optional fields in output.

Tests:

- fresh title/summary/source change;
- null clearing;
- no-op patch;
- compatible replay;
- stale target;
- wrong item type;
- archived item rejection.

Exit criteria:

- Update commands can be implemented and tested without touching event/task detail semantics.

## Slice 7: Event Reschedule

Purpose: Implement one concrete event occurrence reschedule.

Implementation:

- Add `event.reschedule`.
- Replace start/end anchors in a new version.
- Accept optional common patch.
- Detect no-op anchor and patch state.
- Preserve deterministic response shape and receipt semantics.

Spec/fixture decisions:

- Pin timed event reschedule fixture.
- Pin all-day event reschedule fixture.
- Pin no-op reschedule fixture.
- Pin cancelled event rejection fixture.

Tests:

- fresh reschedule;
- no-op reschedule;
- compatible replay;
- stale target;
- cancelled event rejection;
- invalid replacement anchor shape.

Exit criteria:

- Event temporal mutation is deterministic and replay-safe.

## Slice 8: Lifecycle And Archive Commands

Purpose: Complete MVP terminal state transitions.

Implementation:

- Add `event.cancel`.
- Add `task.complete`.
- Add `task.cancel`.
- Add `item.archive`.
- Create receipts for all successful branches.
- Preserve cancellation timestamps as command/audit/receipt facts and shell update timestamps, not detail fields.
- Enforce terminal duplicate ordering before stale rejection.

Spec/fixture decisions:

- Pin fresh and replay fixtures for every lifecycle command.
- Pin terminal duplicate failure fixtures.
- Pin archive replay receipt facts.

Tests:

- fresh lifecycle transitions;
- compatible replay;
- terminal duplicate with different command ID;
- stale target ordering;
- post-archive immutability.

Exit criteria:

- MVP item lifecycle is complete through command core and CLI.

## Slice 9: Relations

Purpose: Add dependency/containment relationship authoring and inspection.

Implementation:

- Add `relation.create`.
- Add `relation.list`.
- Create relation audit and command receipt for fresh create.
- Support compatible replay.
- Reject stale or archived endpoints.
- Reject derived alias relation types on create.
- Return stored rows and derived aliases deterministically in list.

Spec/fixture decisions:

- Pin stored `depends_on` create/list fixture.
- Pin derived `blocks` alias fixture.
- Pin duplicate relation failure fixture.

Tests:

- fresh create;
- compatible replay;
- duplicate relation conflict;
- stale source/target;
- archived endpoint rejection;
- list direction/filter/derived alias behavior.

Exit criteria:

- Agents can create and inspect item dependency graph facts.

## Slice 10: Reminder Create

Purpose: Implement durable reminder intent and generated work without sending externally.

Implementation:

- Add `reminder.create`.
- Require explicit `eligible_at_utc`.
- Resolve `work_subject_ref`.
- Validate OpenClaw binding for `channel=whatsapp` fresh and duplicate-safe success.
- Synthesize trigger anchor when absent.
- Create next item version, notification policy, generated work instance, audit row, and command receipt.
- Implement `if_absent=true` duplicate-safe receipt-only success.
- Never create side-effect attempts or send externally.

Spec/fixture decisions:

- Pin fresh eligible-time-only reminder fixture.
- Pin explicit trigger-anchor reminder fixture.
- Pin `if_absent=true` duplicate receipt-only fixture.
- Pin same-command replay without current OpenClaw binding.
- Pin missing binding failure.

Tests:

- fresh reminder;
- compatible replay;
- duplicate without `if_absent` conflict;
- duplicate with `if_absent` receipt-only success;
- stale-version precedence;
- unsupported channel;
- unresolved `work_subject_ref`;
- missing OpenClaw binding;
- no side-effect attempt.

Exit criteria:

- Reminder authoring is complete for MVP and remains no-send.

## Slice 11: Dry Run Across Writes

Purpose: Make dry-run behavior real and uniform.

Implementation:

- Thread `CommandContext.dry_run` through write handlers.
- Run validation, replay checks, duplicate checks, ID derivation, and response construction.
- Persist nothing.
- Return deterministic would-be IDs where non-dry-run would create rows.
- Return stored IDs for replay branches.
- Return would-be command receipt IDs for no-op and duplicate-safe receipt-only branches.

Spec/fixture decisions:

- Pin dry-run fixture for fresh create.
- Pin dry-run no-op update fixture.
- Pin dry-run duplicate-safe reminder fixture.
- Pin dry-run failure fixture.

Tests:

- row counts unchanged;
- would-be IDs match later non-dry-run when state is unchanged;
- read-only DB dry-run preflight succeeds;
- non-dry-run write preflight still enforces writability.

Exit criteria:

- Dry run is a safe deterministic preview path for write commands.

## Slice 12: CLI Completion

Purpose: Expose the complete MVP command contract through the CLI.

Implementation:

- Add CLI command aliases for all MVP commands.
- Support JSON input for every command.
- Add flag-built forms only where worth the UX cost; JSON input remains canonical.
- Implement `--if-absent`.
- Implement `--generate-command-id` for flag-built write requests only.
- Implement exact exit code mapping.
- Keep stderr human-readable only; stdout remains one structured JSON response.

Spec/fixture decisions:

- Pin generated-command-ID fixture with DB path normalization.
- Pin representative CLI JSON for each command family.
- Decide whether every field has a flag-built form or only common convenience paths.

Tests:

- each command reaches command core;
- unsupported commands and unsupported fields;
- command ID omission;
- generated command IDs;
- preflight categories;
- pretty output;
- exact exit codes.

Exit criteria:

- CLI/command contract is complete for MVP commands.

## Slice 13: Contract Schema And Fixture Packaging

Purpose: Turn executable examples into reusable public contracts.

Implementation:

- Add `contracts/schemas/` only after the fixture-backed response shapes settle.
- Generate or hand-author JSON Schemas for command requests/responses.
- Keep schemas aligned with fixtures by test.
- Add fixture manifest with schema version, command, branch, and expected exit code.

Spec/fixture decisions:

- Decide whether schema files are canonical in MVP or generated from implementation.
- Add spec reference to contract schemas once stable.

Tests:

- every golden fixture validates against the corresponding schema;
- intentional negative fixtures fail validation.

Exit criteria:

- Contract examples and schemas are a public compatibility surface.

## Slice 14: Whetstone Verification And Ratification

Purpose: Use Whetstone as a verifier after implementation has executable anchors.

Run order:

1. Focused diagnostic on response schema and receipt behavior.
2. Focused diagnostic on CLI adapter behavior.
3. Full `utility_mvp` diagnostic sweep.
4. If clean enough, run a bounded Phase 1 verification campaign.

Expected outcome:

- Remaining Whetstone findings should map to specific fixture or schema changes, not broad prose expansion.

Exit criteria:

- No blockers.
- No majors that affect MVP command implementation.
- Source spec, fixtures, schemas, and implementation agree.

## Slice 15: Done Definition For Complete MVP CLI/Command Contract

The CLI/command contract is complete when:

- all MVP commands in `specs/agent-command-contract.md` dispatch through `spine.commands.handle`;
- all command responses have golden fixtures;
- all write commands create or preview command receipts consistently;
- replay, stale-version, archived-item, wrong-type, duplicate, and dry-run behavior have tests;
- CLI returns one structured JSON response and normative exit codes;
- no authoring command sends externally;
- source spec points to executable fixtures/contracts;
- Whetstone diagnostics find no implementation-blocking issues.
