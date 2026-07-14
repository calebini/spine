# Delivery Target Routing Implementation Plan

Status: Working implementation plan
Scope: Implement first-class subject and group delivery targets after Decision 0002

This document is non-normative. If it conflicts with `specs/ontology.md`, `specs/agent-command-contract.md`, or `specs/decisions/0002-first-class-delivery-targets.md`, the specs win.

## Readiness

The design is ready for implementation as a staged migration, not as one large runtime rewrite.

Whetstone audit `whetstone_runs/delivery-targets-group-audit-004` passed with `boundary_preserved=true`. The implementation target is now clear enough:

- recipient owner identity and adapter endpoint identity are separate;
- group delivery is first-class through `subject_groups` and group-owned `delivery_targets`;
- production-like deliverable reminders require a selected active `delivery_target_id`;
- generated routed reminder work snapshots that `delivery_target_id`;
- `work_subject_ref` remains non-routing provenance only;
- OpenClaw derives outbound `target_ref` from `delivery_target_id`, not from subject or group IDs.

Do not treat the existing canary shortcut as production behavior. Existing `work_subject_ref`-only behavior remains a legacy compatibility path until the routing slice lands.

## Non-Goals

- Do not add fanout from a group to individual member targets.
- Do not broaden supported reminder channels beyond the spec-approved first slice.
- Do not introduce a second notification-specific attempt ledger.
- Do not make `subject_kind=group` or `subject_kind=channel_target`.
- Do not require Foreman/Threshold approval in this slice.

## Slice 1: Schema And Migration

Purpose: add the durable routing model while preserving existing ledgers.

Implementation:

- Bump `CURRENT_SCHEMA_VERSION`.
- Add a migration after `0003_add_command_receipts.sql`.
- Add `subject_groups`.
- Add `subject_memberships` only if needed for owner validation or tests; otherwise defer membership behavior while keeping group-owned delivery targets usable.
- Add `delivery_targets` with:
  - `delivery_target_id`
  - `owner_kind`
  - `owner_subject_id`
  - `owner_group_id`
  - `channel`
  - `adapter_name`
  - `account_id`
  - `target_ref`
  - `display_name`
  - `status`
  - `created_at_utc`
  - `updated_at_utc`
- Add owner-kind checks so exactly one owner reference is present.
- Add active-target uniqueness with partial indexes:
  - active target with `account_id IS NULL`: `(adapter_name, channel, target_ref)`
  - active target with `account_id IS NOT NULL`: `(adapter_name, account_id, channel, target_ref)`
- Extend `notification_policies` with:
  - `recipient_kind`
  - `recipient_group_id`
  - `delivery_target_id`
- Preserve legacy rows by backfilling `recipient_kind='subject'` for existing policies.
- Keep existing `recipient_subject_id` valid for legacy subject-recipient policies.
- Add kind-specific duplicate prevention for first-class policies:
  - subject recipients: active uniqueness by `(item_id, version, recipient_subject_id, trigger_anchor_id)`
  - group recipients: active uniqueness by `(item_id, version, recipient_group_id, trigger_anchor_id)`
- Extend `work_instances` with `delivery_target_id`.
- Add indexes for routed policy/work lookups.
- Update `schema.sql`, `EXPECTED_SCHEMA_TABLES`, and `EXPECTED_SCHEMA_INDEXES`.

Tests:

- fresh schema contains new tables, columns, checks, and indexes;
- migration from schema version 3 preserves existing reminder rows as `recipient_kind='subject'`;
- invalid delivery target owners are rejected;
- duplicate active targets are rejected by the correct partial index;
- subject and group policy duplicate rules reject duplicates despite nullable recipient columns;
- `verify_schema` catches missing routing tables/indexes.

Exit criteria:

- Empty ledgers initialize at the new schema version.
- Version 3 ledgers migrate without losing legacy reminder data.
- Ledger verification proves the new routing structures exist.

## Slice 2: Ledger Models And Supporting APIs

Purpose: expose routing facts through the canonical ledger boundary.

Implementation:

- Add dataclasses or typed inputs for:
  - `SubjectGroupInput`
  - `DeliveryTargetInput`
  - first-class notification policy recipient owner fields
- Add ledger helpers to upsert/create subject groups if needed for tests and canary setup.
- Add ledger helpers to create/read delivery targets.
- Extend `NotificationPolicyInput` and copy-forward logic to carry `recipient_kind`, `recipient_group_id`, and `delivery_target_id`.
- Extend current item reads and `item.show` supporting rows to include first-class recipient owner and `delivery_target_id` while preserving legacy output compatibility.
- Extend `generate_notification_reminder_work` so first-class policies with `delivery_target_id` generate work that snapshots that target.
- Reject deliverable routed work generation from first-class policies without `delivery_target_id`.
- Preserve legacy generation for legacy subject-only policies until the command/runtime migration is complete.

Tests:

- group-owned delivery target can be inserted and read;
- subject-owned delivery target can be inserted and read;
- notification policy copy-forward preserves recipient owner and selected target;
- first-class routed work snapshots `delivery_target_id`;
- first-class policy without target remains inert for adapter delivery;
- legacy policy work generation still behaves as before.

Exit criteria:

- Internal ledger APIs can represent group delivery without command-layer shortcuts.
- Existing tests for legacy reminder creation still pass.

## Slice 3: Command Contract Routing Surface

Purpose: add agent-operable routing commands and revise `reminder.create` without breaking legacy fixtures.

Implementation:

- Add `subject_group.upsert` or a narrower `group.upsert` command if command-level group creation is needed for agent workflows.
- Add `delivery_target.upsert` for explicit target management.
- Add first-class `reminder.create` request fields:
  - `recipient_kind`
  - `recipient_subject_id` or `recipient_group_id`
  - `delivery_target_id`
- Keep legacy `work_subject_ref` accepted only as a compatibility path.
- For first-class routed reminders:
  - require active delivery target;
  - require target owner matches recipient owner;
  - require `channel` matches target channel;
  - derive generated policy/work IDs as before;
  - persist `delivery_target_id` on policy and work;
  - set `work_subject_ref` as provenance only:
    - `subject:<subject_id>`
    - `subject_group:<group_id>`
  - update `predicted_delivery` to include `delivery_target_id` and omit or de-emphasize legacy `work_subject_ref` as a destination.
- Keep authoring no-send boundary.
- Define replay and duplicate identity for first-class routed reminders as:
  - target item;
  - recipient owner;
  - channel;
  - delivery target;
  - eligible time.

Fixtures:

- group upsert success/replay if command is added;
- delivery target upsert for subject owner;
- delivery target upsert for group owner;
- routed group reminder success;
- routed subject reminder success;
- routed reminder dry run;
- target-owner mismatch failure;
- inactive target failure;
- channel-target mismatch failure;
- first-class policy without target rejected for deliverable reminder creation;
- legacy `work_subject_ref` reminder fixture remains valid.

Tests:

- first-class routed reminder creates policy/work with matching `delivery_target_id`;
- group recipient does not require fake subject rows;
- replay compatibility includes delivery target facts;
- duplicate-safe `if_absent=true` works for routed reminders;
- dry run returns would-be routed IDs without persistence;
- legacy reminder tests continue passing.

Exit criteria:

- Agents can create a group-owned WhatsApp target and attach a reminder to it without using a WhatsApp JID as a subject ID.

## Slice 4: OpenClaw Adapter Routing

Purpose: stop deriving OpenClaw `target_ref` from `work_subject_ref` for first-class routed work.

Implementation:

- Update OpenClaw outbound builder:
  - if `work_instances.delivery_target_id` is present, load `delivery_targets`;
  - require `adapter_name='openclaw'`;
  - require active target;
  - require channel compatibility;
  - set outbound `target_ref` from `delivery_targets.target_ref`;
  - keep `work_subject_ref` only as provenance in request metadata if useful.
- Keep legacy fallback for work rows with no `delivery_target_id`, but mark it compatibility-only in code/tests.
- Add deterministic blocked outcomes for:
  - missing delivery target;
  - inactive target;
  - owner mismatch discovered at runtime;
  - adapter/channel mismatch;
  - blank target ref.
- Ensure `side_effect_attempts.request_envelope` contains the selected target snapshot.

Tests:

- OpenClaw outbound for group target uses `delivery_targets.target_ref`;
- OpenClaw outbound for subject target uses `delivery_targets.target_ref`;
- legacy work row still maps through `work_subject_ref` until removed;
- inactive/missing/mismatched targets block before external send;
- fake sender and gateway sender tests continue to pass.

Exit criteria:

- Production-like OpenClaw sends never use canonical subject/group IDs as transport destinations.

## Slice 5: Canary And Operator Workflow

Purpose: replace the disposable canary shortcut with a first-class group target path.

Implementation:

- Update `seed_canary_reminder` or add a new routed canary command.
- Canary setup should create:
  - a subject or agent actor;
  - a `subject_group` for the stage WhatsApp group;
  - a group-owned `delivery_target` with the WhatsApp group JID;
  - a routed reminder whose work snapshots `delivery_target_id`.
- Update operator output to show:
  - recipient owner;
  - delivery target ID;
  - channel;
  - target ref preview;
  - no external send unless active runtime opt-in is used.
- Keep legacy canary path only if needed for compatibility testing, clearly labeled.

Tests:

- routed canary creates no fake person subject for the WhatsApp group JID;
- preview envelope uses target from `delivery_targets`;
- `--if-absent` reuses existing routed canary rows safely;
- legacy canary tests either remain scoped or are replaced.

Exit criteria:

- Stage WhatsApp canary can run end-to-end through the routed model.

## Slice 6: Migration Cleanup And Compatibility Policy

Purpose: make the transition explicit and prevent accidental new shortcut use.

Implementation:

- Add warnings or validation to discourage new production-like use of `work_subject_ref` as a transport address.
- Document legacy compatibility behavior in `docs/AGENT_OPERATOR_GUIDE.md`.
- Add a verifier or focused test that rejects target-looking subject IDs for first-class routed paths.
- Decide whether to keep legacy path indefinitely or gate it behind a compatibility flag after routed canary is stable.

Tests:

- first-class command path rejects transport endpoints as subject IDs when a delivery target should be used;
- legacy fixtures remain intentionally covered until removal is scheduled.

Exit criteria:

- Operators and agents have one clear production-like routing path.
- Legacy behavior is isolated and cannot be mistaken for the intended model.

## Slice 7: Final Verification

Run focused tests first:

```bash
PYTHONPATH=src python3 -m unittest tests.test_ledger_migrations
PYTHONPATH=src python3 -m unittest tests.test_ledger_supporting_sets
PYTHONPATH=src python3 -m unittest tests.test_agent_command_contract_mvp
PYTHONPATH=src python3 -m unittest tests.test_openclaw_adapter
PYTHONPATH=src python3 -m unittest tests.test_seed_canary_runtime
```

Then run the full suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Run Whetstone after executable behavior and fixtures exist:

- audit the schema/command/adapter transition;
- include `specs/ontology.md`, `specs/agent-command-contract.md`, Decision 0002, and this implementation plan;
- treat any blocker/major as a patch-before-canary issue.

## Done Definition

The routing implementation is done when:

- schema migration supports `subject_groups`, `delivery_targets`, and routed policy/work columns;
- subject-owned and group-owned targets are both tested;
- routed reminder creation persists recipient owner and selected delivery target;
- generated work snapshots `delivery_target_id`;
- OpenClaw outbound uses delivery target facts for production-like work;
- legacy `work_subject_ref` shortcut remains covered only as compatibility behavior;
- routed stage WhatsApp canary succeeds without creating a fake person subject for the group JID;
- full tests pass;
- Whetstone change audit passes for the implemented transition.
