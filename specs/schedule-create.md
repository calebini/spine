# Spine Atomic Schedule Creation

Status: Implemented v2 on current ledger schema 12
Scope: One atomic operator-facing command for creating a scheduled event or task with notification policies and optional bounded work materialization
Created: 2026-08-12

## 1. Purpose

`schedule.create` is Spine's high-level authoring command for the common operator intent “create this event or task and remind this recipient.” It accepts one normalized request, creates the item and its initial notification-policy set, optionally establishes recurrence provenance, optionally materializes a bounded notification horizon, and returns one deterministic composite receipt.

This command removes transport and agent choreography. It does not replace the lower-level `event.create`, `task.create`, `reminder.create`, `occurrence_provenance.regenerate`, `notification.opportunities`, or `notification_work.materialize` contracts. Those commands remain independently useful for explicit workflows and later mutations. `schedule.create` composes the same canonical models without invoking those public handlers as subcommands.

`specs/schedule-operator-tools.md` defines an additive read-only `schedule.build` compiler for relative-event countdown intent and a CLI compact success projection. The compiler produces this contract's ordinary request; the projection consumes this contract's ordinary response. Neither changes the authoring semantics or authority defined here.

`specs/schedule-primary-location.md` defines an additive capability for an optional
`item.primary_location`. Until a runtime advertises that complete contract family, the
field remains unsupported. Once advertised, its authoring, identity, receipt, replay,
and conditional response rules are normative extensions of this command.

The command is an authoring boundary only. It MUST NOT start work, persist a `side_effect_attempts` row, invoke an adapter, or claim delivery.

## 2. Authority and Version Constants

This specification depends on:

- `specs/ontology.md` for item, version, temporal-anchor, notification-policy, work, audit, and receipt authority;
- `specs/recurrence.md` for recurrence normalization, expansion, identity, DST, and occurrence-provenance semantics;
- `specs/notifications.md` for notification schedule normalization, opportunity identity, bounded materialization, reconciliation, and delivery separation;
- `specs/notification-profiles.md` for archetype assignment, profile selection, direct custom additions, and immutable application provenance;
- `specs/agent-command-contract.md` for shared command, replay, error, dry-run, transport, and CLI rules; and
- `specs/architecture.md` for provider-independent orchestration and approval boundaries.

The version facts are:

- `contract_version=spine.schedule-create.v2`;
- `normalization_version=spine.schedule-create-normalization.v1`;
- `response_contract=spine.schedule-create-response.v2`;
- `receipt_contract=spine.schedule-create-receipt.v2`; and
- `canonical_json_version=spine.canonical-json.v1`.

The request and response schemas are `contracts/schemas/schedule-create-request.schema.json` and `contracts/schemas/schedule-create-response.schema.json`.

The current schema-11 runtime implements this surface and declares the complete schedule-create, item-archetype, and notification-profile contract families through `system.info.implemented_contract_versions`. The transport-neutral command identifier is `schedule.create`; the CLI alias is `spine ... schedule create`.

## 3. Boundary and Non-Goals

`schedule.create` owns orchestration over one new item. It does not introduce a new canonical entity, alternative reminder model, second recurrence engine, route-approval system, or delivery path.

The Version 2 contract intentionally supports:

- exactly one new `event` or `task`;
- one required `local_instant` event-start or task-due schedule;
- optional flexible recurrence inheriting that schedule's time basis, timezone, and resolved timezone-database version;
- one shared notification recipient and delivery route;
- one to 32 request-keyed notification policies;
- either no work materialization or one bounded horizon containing at most 1000 actionable opportunities; and
- initial notification policies on item version `1`.

The additive `spine.schedule-primary-location.v1` capability permits zero or one
primary location without changing any of these time, recurrence, route, policy, or
materialization limits.

Version 2 intentionally does not support:

- updates to an existing item;
- all-day, local-date, fixed-UTC, window, event-end, or task-defer anchors;
- selected-occurrence notification policies during initial creation;
- creating, changing, or approving a delivery target;
- different recipients or routes per policy;
- partial or cursor-paged materialization;
- delivery, adapter invocation, candidate-action approval, or side-effect attempts; or
- a “best effort” branch that keeps the item when policy, provenance, expansion, or requested materialization fails.

These exclusions keep the first composite boundary small while preserving the complete lower-level contract family for advanced authoring.

The implemented `schedule.update` and `schedule.cancel` lifecycle surfaces are specified separately in `specs/schedule-operations.md`; their existence does not broaden this creation contract.

## 4. Request Contract

The request is a closed JSON object with exactly these required top-level fields:

- `contract_version`, exactly `spine.schedule-create.v2`;
- `command_id`;
- `actor_subject_id`;
- `created_at_utc`;
- `item`;
- `scheduled_time`;
- `delivery`;
- `notification_plan`; and
- `materialization`.

Unknown fields fail under the public command contract. `command_id`, actor resolution, timestamp encoding, canonical decimal strings, and canonical JSON follow `specs/agent-command-contract.md` and `specs/ontology.md`.

### 4.1 Item

`item` contains required `item_type` and `title`, optional `summary` and `source_ref`, and exactly one type detail object matching `item_type`. When the runtime advertises `spine.schedule-primary-location.v1`, it also accepts optional `primary_location` using the closed create/reference shape in `specs/schedule-primary-location.md`; otherwise that field fails as unsupported.

- `item_type=event` requires `event_detail` and forbids `task_detail`. `event_detail.all_day` is exactly `false`; optional fields are `visibility` and `attendance_policy_ref`. Version 2 creates a scheduled point event without an end anchor.
- `item_type=task` requires `task_detail` and forbids `event_detail`. Optional `task_detail` fields are `priority` and `subject_roles`. `subject_roles` is the complete initial assignee/owner set and follows the lower-level `task.create` role rules: each entry accepts `role=assignee|owner`, accepts `status=active|inactive`, and derives `status=active` when omitted. After per-entry defaulting and before canonical ordering or identity derivation, every `(subject_id, role)` pair MUST be unique regardless of status. A repeated pair, including one whose entries differ only because one is `active` and the other is `inactive`, fails with `invalid_request`, `field=item.task_detail.subject_roles`, and CLI exit `2`.

The command creates the item shell, common version `1`, and matching event or task detail directly. It does not first create an item and then advance it through reminder versions. The returned `current_version` is therefore `"1"`.

### 4.2 Scheduled local time and timezone pin

`scheduled_time` contains:

- `time_basis=local_instant`;
- canonical `local_date`;
- canonical `local_time` including seconds;
- an IANA `timezone`; and
- `timezone_database_version` as exactly one of:
  - `{"kind":"explicit","version":"<exact-version>"}`; or
  - `{"kind":"system_current"}`.

For `explicit`, the named version MUST be available to the executing runtime and is the persisted version. For `system_current`, the handler reads the exact version reported by the same runtime authority as `system.info.timezone_database_version`, resolves it once before mutation, and persists that string everywhere a local schedule requires it. The directive object remains part of the request semantic facts; the resolved string is part of normalized facts and the receipt.

A fresh command MUST resolve the initial local datetime to exactly one UTC instant. A nonexistent or ambiguous initial local datetime fails closed. Version 2 does not silently choose an offset for the initial anchor. The responsible fields are `scheduled_time.local_date` or `scheduled_time.local_time` after timezone and pinned-data validation.

This initial-anchor rule does not change recurrence candidate semantics. After a valid seed is accepted, later recurrence candidates use `specs/recurrence.md`: nonexistent candidates are omitted and ambiguous candidates select the earliest valid UTC instant with deterministic diagnostics.

### 4.3 Optional inherited recurrence

`scheduled_time.recurrence`, when present, contains the initial `rules` and optional `rdates` and `segments` shapes from `spine.recurrence-authoring.v1`, except that it omits `time_basis`, `timezone`, and `timezone_database_version`. Those three facts inherit the accepted `scheduled_time` values.

Before canonical recurrence normalization, the command constructs the ordinary recurrence-authoring object with:

- `time_basis=local_instant`;
- the request `timezone`;
- the resolved timezone-database version; and
- the supplied `rules`, `rdates`, and `segments`.

Every selector, segment-label, default, identity, and validation rule then follows `specs/recurrence.md`. This inheritance is authoring convenience only; the persisted recurrence set is the same canonical model produced by lower-level authoring.

The accepted `scheduled_time` is the recurrence set's seed anchor and supplies `seed_scheduled_fact` for omitted-segment defaulting. It does not rewrite caller-supplied rule seeds, start bounds, rdates, or explicit segment bounds; those facts must independently satisfy the recurrence contract.

### 4.4 Recipient and delivery route

`delivery` contains:

- `recipient_kind=subject` with `recipient_subject_id`, or `recipient_kind=subject_group` with `recipient_group_id`;
- non-empty `channel`; and
- `target`, which is exactly one of:
  - `{"resolution":"explicit","delivery_target_id":"..."}`; or
  - `{"resolution":"context_default","default_key":"..."}`.

An explicit target MUST already exist, be active, have the same recipient owner, and have the same channel. A context default is not ambient inference: the transport MUST provide a normalized `CommandContext.delivery_target_defaults` mapping from `default_key` to exactly one delivery-target ID before handler invocation. The resolved row must satisfy the same owner, status, and channel checks.

Zero matches, multiple matches, an absent key, an inactive target, or an owner/channel mismatch fails before mutation. The command MUST NOT create, update, approve, or reactivate a delivery target. The governance authority or an operator-facing route command remains responsible for approval and route creation.

The fresh receipt snapshots the resolved `delivery_target_id`, `resolution_source`, `default_key` when used, `channel`, `adapter_name`, and `target_ref`. Replay returns that snapshot and MUST NOT resolve the default again or substitute a target that later becomes the context default.

### 4.5 Notification plan and reminder policies

`notification_plan` is the closed create-plan shape from
`specs/notification-profiles.md`. It selects exactly one of `mode=none`,
`mode=explicit`, or `mode=archetype_default`. `mode=none` is the direct authoring
path and requires one through 32 `custom_additions`; it does not create a profile
application. The other modes resolve and snapshot one exact profile revision and may
suppress, replace, or add policies as that specification defines.

Every resulting policy has a unique `policy_key`, a notification `schedule`, and
`late_handling`. Policy-key, set-equivalence, canonical ordering, profile provenance,
and duplicate-normalized-policy rules are defined by `specs/notification-profiles.md`
and `specs/notifications.md`. Array order is not semantic and MUST NOT change
identities or replay compatibility.

For a non-recurring item, each policy is normalized with target `{anchor_role: event_start|task_due, application_scope: item}`. For a recurring item, each policy is normalized with target `{anchor_role: event_start|task_due, application_scope: each_occurrence}`. `selected_occurrence` is impossible before a persisted occurrence exists and is not accepted by this command.

Every policy shares the resolved recipient, channel, and delivery target. The command supplies `authoring_contract=spine.notification-schedule-authoring.v1` internally and otherwise uses `specs/notifications.md` without alternate cadence or identity rules.

## 5. Materialization Horizon

`materialization.mode` is `none` or `bounded`.

### 5.1 No materialization

`{"mode":"none"}` creates the item, recurrence facts when present, initial policies, audit, and command receipt. It does not create occurrence provenance, expand opportunities, or create work. The policies can later be evaluated through the lower-level bounded commands.

### 5.2 Bounded materialization

Bounded materialization requires:

- `mode=bounded`;
- explicit `evaluated_at_utc`;
- decimal-string `limit` in `1..1000`; and
- `range`, exactly one of:
  - `local_range` with inclusive `range_start_local` and exclusive `range_end_local`, each a canonical local datetime without offset; or
  - `item_relative` with signed decimal-string `start_offset_seconds` and `end_offset_seconds` relative to the resolved initial item UTC instant.

For `local_range`, both boundaries use the item timezone and resolved timezone-database version. Each boundary MUST resolve to exactly one UTC instant; ambiguous or nonexistent boundaries fail closed. For `item_relative`, the command adds exact elapsed SI seconds to the resolved initial UTC instant. In both forms, normalized `range_start_utc` MUST be earlier than `range_end_utc`, and the resulting elapsed range MUST satisfy the 366-day notification bound.

The handler performs local-to-UTC conversion. Callers MUST NOT be required to precompute a UTC materialization range.

`evaluated_at_utc` is the evaluation and materialization instant for late-handling decisions and is persisted in the receipt. The command MUST NOT use ambient current time. Replay uses the stored result and does not reevaluate lateness.

The command expands the complete bounded opportunity set before writing work. If the number of selected actionable opportunities exceeds `limit`, it fails with `invalid_request`, `field=materialization.limit`; it MUST NOT materialize a prefix. Zero selected opportunities is a valid completed result.

For recurring items, the command derives the exact occurrence source range required by the normalized UTC opportunity range plus every policy's bounded offsets. It regenerates active occurrence provenance for `consumer=notification_schedule` before opportunity expansion. If that source range cannot be derived exactly, provenance remains unresolved, or any selected occurrence lacks current actionable provenance, the whole command fails.

Every selected actionable opportunity is materialized as one durable `work_instances` row under `specs/notifications.md`. Non-actionable opportunities caused by route, item, policy, recurrence, or reconciliation state are not silently omitted: because all canonical facts are new and controlled by one command, such an outcome is a semantic or environment failure and rolls back the command.

## 6. Atomic Transaction and Persistence

A fresh non-dry-run success is one SQLite transaction. The implementation MUST use internal normalization and persistence services; it MUST NOT dispatch public subcommands that commit independently or manufacture lower-level command receipts.

The ordered logical phases are:

1. validate the closed request and replay identity;
2. verify runtime, current ledger schema, actor, pinned timezone data, and context capability;
3. normalize the item, initial local anchor, optional recurrence, route, policies, and materialization range;
4. begin the write transaction;
5. create the item shell, common version `1`, type detail, temporal anchor, optional recurrence set/revision, and other initial supporting rows;
6. create every notification intent, schedule, and policy as part of the complete version-`1` supporting set;
7. for bounded recurring materialization, derive and persist current occurrence provenance;
8. for bounded materialization, expand the complete opportunity set and create all selected work rows;
9. persist one composite audit row and one `schedule.create` command receipt;
10. run commit-time invariants and commit; and
11. read back the committed identities and compare them with the receipt before returning success.

Any failure before commit rolls back every row created by the command. In particular, there MUST NOT be an item without all requested policies, a policy without requested bounded work, a partial policy array, a partial materialization range, or a command receipt for a rolled-back transaction.

`schedule.create` creates one composite audit row with action and reason `schedule_created`. Canonical child rows retain their ordinary `created_by_command_id` or equivalent creation facts, so the single audit can enumerate item, policy, provenance, opportunity, and work identities without inventing subcommand audits.

## 7. Identity, Receipt, and Replay

Ordinary command-derived item, anchor, audit, and receipt IDs use `command=schedule.create`, the shared `spine.command-id.v1` derivation, and these paths:

- item: `/item`;
- start or due anchor: `/scheduled_time`;
- audit: `/audit`;
- command receipt: `/`;
- task subject roles: `/item/task_detail/subject_roles/<canonical-index>`.

When the primary-location capability is used, its location and item-location paths are
the exact paths registered by `specs/schedule-primary-location.md`.

Recurrence, notification, occurrence, provenance, opportunity, and work identities use their owning content-addressed specifications. For initial notification intent derivation, `intent_created_item_version="1"` and `intent_created_by_command_id` is the composite `command_id`. Policy normalization order is canonical `policy_key` order; `policy_key` is included in the composite receipt mapping but is not added to the existing notification-policy identity preimage.

On fresh non-dry-run success, exactly one `command_receipts` row is written. Compatible replay and dry run write no receipt row. The persisted receipt has:

- `command=schedule.create`;
- `effect=schedule_created`;
- original request semantic facts and their hash;
- `receipt_contract=spine.schedule-create-receipt.v2` in result facts;
- the resolved timezone-database version and initial UTC instant;
- the resolved delivery snapshot;
- item, recurrence, policy, opportunity, work, provenance, and audit identities produced by the request; and
- normalized materialization range and phase states.

The result facts are sufficient to reconstruct the original success response from immutable historical rows and snapshotted route facts. Mutable current item state, a changed context default, a later timezone-data installation, and a changed delivery-target row MUST NOT alter replay output.

Replay ordering is:

1. parse a JSON object and validate the closed request field set sufficiently to construct canonical semantic facts;
2. look up `command_id` globally;
3. reject a receipt for another command with `semantic_conflict`, `field=command_id`;
4. reject a same-command semantic hash mismatch with `semantic_conflict`, `field=command_id`; and
5. for a compatible receipt, reconstruct the stored result from receipt and historical evidence, set only the top-level response `effect=schedule_create_replay`, and return without re-resolving timezone data, context defaults, opportunities, or work.

A compatible replay creates no row and performs no current-environment capability check beyond the ability to read and validate the receipt evidence. If required historical evidence is missing or contradicts the receipt, replay fails with `runtime_failure`; it MUST NOT repair or recreate rows under the old command ID.

## 8. Success Response

A success follows `spine.schedule-create-response.v2` and returns:

- `ok=true`, `command=schedule.create`, `response_contract`, and `effect`;
- `command_id`, `command_receipt_id`, `audit_id`, and `created_at_utc`;
- item identity, type, version `1`, title, and accepted local/UTC schedule facts;
- nullable archetype assignment and the complete notification-profile/direct-plan projection;
- optional `primary_location` exactly when the request supplied it and the runtime
  advertises the primary-location capability;
- optional recurrence set, revision, normalized hash, and timezone-resolution diagnostics;
- the snapshotted delivery resolution and explicit `delivery_state=not_attempted_by_command`;
- policies ordered by `policy_key`, including intent, policy, schedule, and normalized schedule-hash identities;
- materialization state, accepted normalized range, counts, ordered opportunity/work evidence, and `work_instance_ids`;
- one receipt summary containing `receipt_contract`, the command-receipt effect, semantic-facts hash, and receipt timestamp; and
- closed phase states for item, policies, provenance, opportunities, work, and delivery.

The top-level response effect identifies the response branch: fresh success uses `effect=schedule_created`, compatible replay uses `effect=schedule_create_replay`, and a dry-run fresh branch uses `effect=schedule_created` plus `dry_run=true`. The nested `receipt.effect` always reports the command-receipt effect `schedule_created`: the persisted value for fresh success and compatible replay, or that deterministic would-be value for dry run. `schedule_create_replay` is never stored in `command_receipts` and never replaces the nested receipt effect.

Phase values are:

- `item=created`;
- `policies=authored`;
- `provenance=regenerated|not_applicable|not_requested`;
- `opportunities=expanded|not_requested`;
- `work=materialized|completed_zero_selected|not_requested`; and
- `delivery=not_attempted`.

The mapping is exact: without recurrence, provenance is `not_applicable`; with recurrence and `materialization.mode=none`, provenance is `not_requested`; with recurrence and bounded materialization, provenance is `regenerated`. Mode `none` requires opportunities and work `not_requested`. Bounded mode always reports opportunities `expanded`; work is `materialized` when at least one work row is created and `completed_zero_selected` when none is selected.

The opportunity/work evidence array orders by `eligible_at_utc`, `notification_opportunity_id`, then `work_instance_id`. It returns each policy key, notification identities, scheduled eligibility time, optional recurrence occurrence key and scheduled facts, and materialized work identity. `work_instance_ids` uses that same order.

The response never uses `delivered`, `sent`, or an adapter-success value. Delivery is later worker state proven by `side_effect_attempts` and work lifecycle evidence.

CLI callers may request `--compact`, which projects this successful response under `spine.schedule-compact.v1`. Full `spine.schedule-create-response.v2` JSON remains the default, and projection occurs only after canonical command handling. A compact dry run is explicitly marked as a preview.

## 9. Validation and Failure Ordering

For a fresh command, validation precedence is:

1. request-object, required-field, unsupported-field, scalar-format, array-bound, and discriminated-union validation;
2. global command-ID replay or collision handling from Section 7;
3. current ledger schema and declared runtime capability;
4. actor resolution;
5. timezone, timezone-database version, initial-local-time resolution, and materialization-boundary resolution;
6. item/type-detail and optional recurrence normalization;
7. recipient and delivery-target resolution;
8. policy-key uniqueness and notification-policy normalization;
9. materialization range, density, and exact source-range derivation;
10. deterministic identity construction and pre-write collision checks;
11. transactional persistence, provenance, opportunity expansion, work materialization, and commit-time invariants; and
12. post-commit receipt/evidence readback.

Errors use the common public codes and CLI exits. Required fail-closed cases include:

- unavailable or mismatched schema/runtime: `environment_failure` on the responsible schema or contract field;
- unavailable pinned timezone data: `environment_failure`, `field=scheduled_time.timezone_database_version`;
- unknown timezone: `invalid_request`, `field=scheduled_time.timezone`;
- nonexistent or ambiguous initial/boundary local time: `invalid_request` on the responsible local date/time field;
- illegal recurrence or reminder cadence: `invalid_request` on the narrowest recurrence/reminder field;
- duplicate task `(subject_id, role)` pair regardless of status: `invalid_request`, `field=item.task_detail.subject_roles`;
- duplicate policy key: `semantic_conflict`, `field=notification_plan.custom_additions[n].policy_key` or the corresponding profile-composition field;
- absent or ambiguous context default: `referenced_row_not_found` or `semantic_conflict`, `field=delivery.target.default_key`;
- explicit target missing: `referenced_row_not_found`, `field=delivery.target.delivery_target_id`;
- advertised primary-location reference missing: `referenced_row_not_found`,
  `field=item.primary_location.location_id`;
- inactive or owner/channel-mismatched target: `semantic_conflict` on the responsible delivery field;
- invalid or oversized horizon: `invalid_request` on the responsible materialization field;
- more opportunities than the accepted limit: `invalid_request`, `field=materialization.limit`;
- unresolved recurrence provenance: the existing provenance failure code and field from `specs/recurrence.md`; and
- commit or receipt readback mismatch: `runtime_failure` with no partial mutation left open.

If an unexpected failure is detected only after a successful SQLite commit, the command returns `runtime_failure`, preserves the committed receipt as the authoritative replay index, and MUST NOT retry under a new command ID automatically. The implementation must make this branch detectable by comparing committed rows to stored result facts.

## 10. Dry Run, Transport, and Side-Effect Boundary

`schedule.create` supports the shared `dry_run` context. Dry run executes all deterministic validation, current-context resolution, normalization, opportunity expansion, density checks, and would-be identity construction against an isolated transaction or equivalent snapshot. It returns the complete would-be response with `dry_run=true`, persists nothing, and invokes no external system.

CLI transport syntax is `spine --db <path> --input <path-or-> [options] schedule create`, with options before command words. MCP and HTTP transports map to the same canonical request and response. A transport may supply a named delivery-target default only through the normalized command context; it MUST NOT add hidden business defaults to the request or response.

No branch of `schedule.create`, including bounded materialization, may start work or deliver. Materialized rows begin in the ordinary eligible state and can be processed only by the existing Tickerd/worker boundary with explicit runtime mode, adapter binding, durable pre-write attempt, and any required external approval.

## 11. Contract Fixtures and Conformance

`contracts/schedule-create-fixture-manifest.json` indexes structural request and response examples under `tests/fixtures/schedule_create/contracts/`. Structural examples prove schema shape only; they are not computed identity vectors.

Before runtime support is declared, executable tests MUST cover at least:

- one non-recurring event with a two-hour, 20-minute repeat window and bounded materialization;
- one recurring task with inherited every-three-days recurrence and a named context-default route;
- task-role status defaulting plus rejection of duplicate `(subject_id, role)` pairs whose status values differ;
- explicit and `system_current` timezone pinning;
- initial ambiguous and nonexistent local-time rejection;
- local-range and item-relative horizon normalization;
- policy reorder equivalence and duplicate-key rejection;
- explicit/context-default target success, zero-match, multiple-match, inactive, owner mismatch, and channel mismatch;
- policy-only success;
- recurring provenance before opportunities;
- zero-opportunity materialization;
- limit-plus-one rollback with no partial item;
- failure injected after each transactional phase;
- compatible replay after timezone, route-default, target-row, and current-item changes;
- incompatible and cross-command command-ID reuse;
- complete dry-run identity agreement with a later unchanged commit;
- no audit/receipt fan-out into synthetic subcommands; and
- proof that no command branch writes `side_effect_attempts` or invokes an adapter.

Computed vectors MUST publish canonical semantic preimages, normalized timezone and range facts, expected child IDs, receipt result facts, and final digests. Two conforming implementations given the same ledger, command context, and request MUST produce byte-identical normalized facts, identifiers, receipt result facts, and response ordering.

## 12. Acceptance Criteria

The specification is implementation-ready only when:

1. A caller can express a scheduled event or task, optional recurrence, existing explicit or named context-default route, keyed reminders, and bounded-or-none materialization without calculating UTC ranges.
2. Initial local time, timezone pinning, recurrence inheritance, route resolution, policy target derivation, and range normalization are deterministic and fail closed.
3. One fresh success creates exactly one item at version `1`, the complete initial policy set, requested provenance and work, one audit, and one command receipt in one transaction.
4. Any precommit failure leaves none of those rows.
5. Compatible replay returns the original resolved timezone, route snapshot, identities, times, phase states, and work evidence without current-default re-resolution.
6. Policy-only, zero-selected, bounded-materialized, replay, and dry-run branches are distinguishable without implying delivery.
7. The receipt contains every item, notification, route, scheduled-time, provenance, opportunity, work, audit, and semantic-hash fact required for Stage Anchor to verify the result.
8. No direct SQLite authoring is required of agents, and no public subcommand chaining is observable in audit or receipt facts.
9. No branch creates a side-effect attempt or invokes an external adapter.
10. The schemas, fixtures, vectors, implementation-version declaration, runtime behavior, and agent/operator documentation land together before the command is advertised as implemented.
