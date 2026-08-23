# Spine Operational Schedule Lifecycle

Status: Implemented contract on current schema 9
Scope: Cross-item agenda readback, atomic whole-schedule mutation, terminal cancellation, and notification-work reconciliation
Created: 2026-08-16

## 1. Purpose

Spine already provides atomic schedule creation, single-item verification, lower-level item and recurrence mutations, notification-policy lifecycle commands, bounded opportunity expansion, and durable work materialization. This specification closes the operator lifecycle around those capabilities.

The version-1 operational family contains:

- `agenda.show`, a read-only cross-item local-time range projection;
- `schedule.update`, one atomic whole-schedule mutation and reconciliation command; and
- `schedule.cancel`, one type-neutral terminal cancellation and reconciliation command.

These commands remove agent choreography. They do not introduce an agenda entity, second recurrence engine, second notification model, adapter route authority, or alternate attempt ledger. Canonical truth remains in existing item, recurrence, policy, provenance, work, audit, receipt, and `side_effect_attempts` rows.

## 2. Authority and Version Facts

This specification depends on:

- `specs/ontology.md` for item, version, lifecycle, work, audit, receipt, and attempt authority;
- `specs/recurrence.md` for recurrence normalization, revisions, occurrence identity, expansion, and provenance;
- `specs/notifications.md` for policy identity, opportunity expansion, work materialization, reconciliation, and cancellation reason precedence;
- `specs/schedule-create.md` for composite transaction and route-resolution posture;
- `specs/schedule-show.md` for current single-item schedule and delivery evidence;
- `specs/agent-command-contract.md` for shared command, replay, stale-version, error, dry-run, and CLI rules; and
- `specs/architecture.md` for provider-independent orchestration and external-side-effect boundaries.

The implemented version facts are:

- `spine.schedule-operations-normalization.v1`;
- `spine.schedule-agenda.v1` and `spine.schedule-agenda-response.v1`;
- `spine.schedule-update.v1`, `spine.schedule-update-response.v1`, and `spine.schedule-update-receipt.v1`; and
- `spine.schedule-cancel.v1`, `spine.schedule-cancel-response.v1`, and `spine.schedule-cancel-receipt.v1`.

The exact machine shapes live in `contracts/schemas/schedule-agenda-*.schema.json`, `contracts/schemas/schedule-update-*.schema.json`, and `contracts/schemas/schedule-cancel-*.schema.json`.

The runtime advertises these facts through `system.info.implemented_contract_versions`. Behavioral conformance, including agenda snapshot pagination, atomic update/reconciliation/materialization, cancellation, replay, dry run, and no-send behavior, lives in `tests/test_schedule_operations_command.py`.

## 3. Shared Boundary

Version 1 intentionally operates on `event` and `task` items. It owns no project, collection, dependency, approval, projection, or vendor synchronization behavior.

The write commands:

- require caller-supplied `command_id`, actor, target item, exact `target_version`, and explicit action timestamp;
- resolve compatible replay before target-version freshness;
- reject archived or wrong-type items;
- preserve immutable prior item versions, recurrence revisions, policies, work, attempts, audits, and receipts;
- create at most one next item version per command;
- invoke no adapter and persist no `side_effect_attempts` row; and
- return one deterministic composite receipt rather than synthetic lower-level receipts.

Occurrence-specific moves, exclusions, overrides, and lifecycle changes remain under `recurrence.instance.*`. Split or segmented recurrence edits remain under `recurrence.series.edit`. `schedule.update` is a whole-item and whole-series operator surface, not a replacement for those precise commands.

### 3.1 Granularity-Preservation Invariant

Every high-level schedule effect MUST decompose completely into the existing canonical Spine row families and their stable identities. No item, temporal, recurrence, occurrence-provenance, notification-intent, notification-policy, routing, work, audit, receipt, or delivery-attempt fact may exist only as an opaque field of the composite request, response, or receipt.

The composite commands may coordinate several canonical mutations under one transaction and one composite audit/receipt, but they MUST NOT flatten, merge, overwrite, or replace the underlying immutable facts. Their responses and receipts MUST expose the prior and successor identities, per-policy effects, and work reconciliation classifications needed to inspect that decomposition through canonical read surfaces.

The lower-level item, recurrence, notification, work, and lifecycle commands remain authoritative precision surfaces for mutations outside the composite command's declared scope. Implementing this family MUST NOT remove, weaken, reinterpret, or make unreachable those finer-grained contracts. `agenda.show` is only a projection; omission or summarization in that view never removes detail available through `schedule.show` or the owning lower-level read contract.

## 4. `agenda.show`

### 4.1 Purpose and Request

`agenda.show` answers “what is scheduled in this local range?” without raw SQL, caller-known item IDs, or per-item occurrence queries. It is read-only and creates no receipt.

The closed request requires:

- `contract_version=spine.schedule-agenda.v1`;
- `evaluated_at_utc`, used for task defer state and notification/work summaries;
- `range_start_local` and exclusive `range_end_local`, canonical local datetimes including seconds;
- an IANA `timezone` defining the agenda view;
- `timezone_database_version` as the same `explicit` or `system_current` directive accepted by `schedule.create`; and
- decimal-string `limit` in `1..1000`.

Optional fields are:

- `item_types`, a unique subset of `event|task`, default both;
- `item_ids`, a unique narrowing set of at most 100 IDs;
- `include_terminal`, default `false`;
- `include`, a unique subset of `notification_summary|work_summary` plus
  `primary_location` when the runtime advertises
  `spine.schedule-primary-location.v1`, default empty;
- `include_diagnostics`, default `false`; and
- `cursor` for the next page.

The local range boundaries MUST each resolve to one UTC instant under the accepted view timezone and concrete timezone-database version. Nonexistent or ambiguous boundaries fail closed. The normalized half-open UTC range MUST be non-empty and no longer than 366 elapsed days. `system_current` is resolved once per first-page request; the concrete version is returned and cursor-bound.

### 4.2 Selection and Expansion

The command reads only current item truth. Archived shells are excluded. Unless `include_terminal=true`, cancelled events and done or cancelled tasks are excluded. With `include_terminal=true`, terminal items and terminal recurrence overrides may appear with `actionable=false` and their lifecycle facts intact.

One entry is produced for each matching primary schedule fact:

- `event_start` for events; or
- `task_due` for tasks.

An event end is returned on its event-start entry when present. A task defer-until anchor does not create a second agenda entry; it contributes defer state and may make the task non-actionable at `evaluated_at_utc`.

Non-recurring point anchors are selected when their expressed instant lies in the half-open normalized range. UTC or local windows are selected when their half-open interval overlaps the normalized range. A `local_date` anchor occupies that complete calendar date in the agenda view timezone and is selected on local-day overlap.

Recurring primary anchors expand through `specs/recurrence.md` using expressed-time selection. Exdates remain omitted, moved occurrences are selected by expressed time, duplicate collapse remains canonical, and occurrence lifecycle/detail overlays are applied before agenda actionability. The entry returns current `recurrence_revision_id` and `occurrence_key`; agenda projection does not create occurrence provenance.

A stored local instant MUST resolve using its own pinned timezone and timezone-database version before conversion to the agenda view. An unavailable required pinned version fails closed; the command MUST NOT resolve using different timezone data or silently omit the entry. Recurrence nonexistent-time omission and deterministic ambiguous-time selection remain governed by `specs/recurrence.md` and may emit diagnostics.

Items without a primary scheduled anchor are omitted. When diagnostics are requested, each omission emits `agenda_item_unscheduled` with `item_id` and `field=primary_schedule`. Other closed agenda diagnostics are `agenda_recurrence_candidate_omitted` with `field=recurrence` and `agenda_terminal_excluded` with `field=detail_status`. Every diagnostic requires `field`. Diagnostics are ordered by code, item ID, optional occurrence key, then field, with an absent occurrence key sorting before a present value.

### 4.3 Entry View and Ordering

Each entry returns:

- item ID, current version, type, title, shell status, and event/task detail status;
- occurrence kind `single|recurring`, primary anchor role, canonical source `anchor_kind`, and actionability;
- original and expressed scheduled facts;
- agenda-view local date/time plus deterministic `sort_at_utc`;
- source timezone and concrete timezone-database version when applicable;
- start UTC and optional end UTC;
- optional recurrence revision and occurrence key;
- task defer state when applicable; and
- requested notification/work summaries.

For a point anchor, `start_at_utc` and `sort_at_utc` are its resolved instant. For `utc_window` or `local_window`, `start_at_utc` is the window's resolved start and `end_at_utc` is its exclusive end. For `local_date`, agenda projection derives both from midnight-to-midnight in the agenda view timezone under the response's concrete timezone-database version; `sort_at_utc` equals that derived start. These derived agenda instants are response facts only and MUST NOT be persisted back into the source anchor.

The total ordering is:

1. agenda-view local date;
2. all-day entries before timed entries;
3. `sort_at_utc`;
4. anchor role order `event_start`, then `task_due`;
5. item ID; and
6. occurrence key, with the empty single-item key sorting first.

Notification summary reports current active policy count and optional next actionable opportunity at or after `evaluated_at_utc` within the normalized agenda range. Work summary reports complete item-linked status counts and optional next currently actionable eligible work instant. Neither summary treats policy authoring, opportunity expansion, work materialization, or delivery as equivalent facts.

### 4.4 Snapshot and Cursor

The first page derives `query_hash` from canonical JSON containing the normalized concrete request except `cursor`. It derives `source_snapshot_hash` from the sorted current facts capable of changing selected entries or requested summaries:

- item IDs, current versions, shell and detail lifecycle;
- primary temporal-anchor identities and facts;
- current recurrence set and revision identities;
- current policy IDs, intent IDs, status, normalized schedule hashes, target, and routing facts when either notification or work summary is included; and
- matching work IDs, eligibility, status, and attempt count when work summary is included.
- the clean current primary-location view or JSON `null` when `primary_location` is
  included, as defined by `specs/schedule-primary-location.md`.

The cursor is an opaque integrity-checked encoding of normalization version, query hash, source snapshot hash, and last emitted ordering tuple. A next-page request MUST repeat every non-cursor request fact byte-for-byte. Any query mismatch fails with `invalid_request`, `field=cursor`; any changed source snapshot fails with `stale_cursor`, `field=cursor`. The command never continues against a silently changed agenda snapshot.

The response returns `limit`, `has_more`, required nullable `next_cursor`, both hashes, the concrete normalized range, ordered entries, requested `included` values, and optional diagnostics. `next_cursor` is a non-empty opaque string exactly when `has_more=true` and is JSON `null` when `has_more=false`. It returns no redundant `truncated` flag.

## 5. `schedule.update`

### 5.1 Purpose and Request

`schedule.update` atomically changes current schedule truth, reconciles obsolete notification work, optionally materializes a bounded replacement horizon, and returns one receipt plus current schedule evidence.

The closed request requires:

- `contract_version=spine.schedule-update.v1`;
- `command_id`, `actor_subject_id`, `item_id`, `target_version`, and `updated_at_utc`;
- non-empty `patch`; and
- `materialization`, explicitly `none` or `bounded`.

The target MUST be an active-shell scheduled event or open task whose primary event-start or task-due anchor has `anchor_kind=local_instant`. This target-shape requirement applies to every Version 1 patch dimension, including item-only, reminder-only, delivery-only, and reconciliation-only updates; another primary anchor kind fails with `invalid_request`, `field=primary_schedule.anchor_kind`. A terminal detail state fails with `invalid_state_transition`, `field=detail_status`.

An otherwise eligible event may retain an end anchor while receiving an item, recurrence, delivery, reminder, or reconciliation-only update. When such an event has an end anchor, a request containing `patch.scheduled_time` fails with `invalid_request`, `field=patch.scheduled_time`, because Version 1 defines neither implicit duration preservation nor end-anchor replacement. Callers use `event.reschedule` for that temporal mutation until a later composite duration contract exists. The end anchor alone does not make non-time patch dimensions ineligible.

The patch may contain `item`, `scheduled_time`, `recurrence`, `delivery`, and `reminders`. A runtime advertising `spine.schedule-primary-location.v1` additionally accepts `primary_location` with omit-to-retain, null-to-clear, and closed create/reference replacement semantics from `specs/schedule-primary-location.md`. Omitted dimensions copy current truth exactly. At least one dimension is required, although normalized equality may produce a no-op.

### 5.2 Item and Scheduled-Time Patch

`item` may patch common `title`, `summary`, and `source_ref`; event `visibility` and `attendance_policy_ref`; or task `priority` and the complete assignee/owner `subject_roles` set. Title cannot be null or empty. Nullable fields use explicit `null` to clear and omission to preserve. Role normalization and semantic uniqueness follow `task.update`.

`scheduled_time`, when present, is a complete replacement local instant containing local date, local time, timezone, and timezone-database directive. It resolves exactly as a fresh `schedule.create` initial anchor: the accepted local time MUST be unambiguous and existent, and the concrete version and UTC instant are receipt facts. The replacement writes a new temporal anchor; it never mutates the prior row.

If current recurrence exists, changing `scheduled_time` requires a `recurrence` replacement in the same request. This prevents the anchor from moving while rule seeds silently remain on the old series. If there is no current recurrence, scheduled time may change alone.

### 5.3 Whole-Series Recurrence Replacement

`recurrence` supports exactly `mode=replace` plus the complete inherited `rules` and optional `rdates` and `segments` shape from `schedule.create`. It inherits the replacement scheduled time when present, otherwise the current scheduled time.

For an existing recurrence set, replacement creates its next immutable revision under whole-series semantics and records lineage. For a non-recurring item, replacement creates the initial recurrence set bound to the resulting item version. Rule, segment, selector, identity, normalization, timezone, diagnostic, and density semantics remain wholly owned by `specs/recurrence.md`.

Version 1 does not remove recurrence, split a series, or edit one occurrence. An attempted empty replacement is invalid; detaching a recurring item into a singleton remains deferred until retirement and downstream-provenance semantics are specified.

### 5.4 Reminder Replacement and Delivery

`reminders`, when present, is the complete desired active reminder set and contains zero through 32 entries ordered canonically by unique `policy_key`.

Each entry contains `policy_key`, schedule, and late handling. An existing intent additionally requires its current `notification_intent_id` and `notification_policy_id`; a new intent omits both. Supplying only one identity is invalid. Each referenced current policy MUST belong to the target item/version and be active. A current active intent omitted from the desired set receives a disabled successor. Disabled intents are not re-enabled, and a historical policy key cannot be rebound to another intent.

For items first entering this composite surface, the caller may assign a new unique policy key to each referenced current active intent. The successful receipt establishes the stable key-to-intent mapping for later composite updates. On later calls, a key/intent mismatch against the latest compatible composite receipt fails with `semantic_conflict`, `field=patch.reminders[n].policy_key`.

`delivery`, when present, uses the same subject/group, channel, and explicit/context-default target shape and validation as `schedule.create`. It applies to the complete resulting active policy set. When reminders are omitted, delivery retargets all current active policies. When reminders are present, policies omitted from that desired set are disabled rather than retargeted. When reminders contain a new intent and delivery is omitted, the request is invalid because no route can be inherited for that new intent. Existing reminder entries preserve their current routes when delivery is omitted.

Policies normalize through `specs/notifications.md`. Equal entries are copied forward under their existing intent, changed entries create successor policies, new entries create new intents, and omitted entries create disabled successors. Duplicate normalized policies remain a semantic conflict even when policy keys differ.

### 5.5 Mandatory Reconciliation and Optional Materialization

Every update computes notification-work freshness after normalized successor truth is known. A work row is cancellable by reconciliation only when all are true:

- `status=eligible`;
- `attempt_count=0`;
- no `side_effect_attempts` row references it; and
- its current schedule, target, occurrence, route, policy, or parent lifecycle is no longer actionable.

Cancellation uses the base executable-v1 closed reason-code precedence from `specs/notifications.md`: `notification_schedule_superseded`, `notification_target_changed`, `notification_occurrence_stale`, `notification_routing_changed`, `notification_policy_disabled`, then `parent_lifecycle_terminal`. A runtime advertising `spine.relative-temporal-binding.v1` imports the notification contract's conditional extension by inserting `notification_temporal_binding_stale` after `notification_occurrence_stale` and before `notification_routing_changed`; runtimes that do not advertise that family MUST NOT return the added value.

An existing row selected by the reconciliation or materialization evaluation is returned in `retained_work_instance_ids` exactly when its notification intent, schedule hash, target, route, occurrence provenance, and parent lifecycle remain semantically current under successor truth, so no cancellation reason applies. When `spine.relative-temporal-binding.v1` is advertised and the target task due anchor has an active `follow_source` binding, retention additionally requires the binding state to be exactly `current` and the current due anchor to equal the latest binding revision's target anchor. Retention leaves the row and its lifecycle unchanged; it may cross unchanged policy copy-forward as permitted by `specs/notifications.md`. A retained eligible row remains subject to the normal attempt-start freshness gate, while retained in-progress or terminal rows are evidence rather than new authorization.

In-progress work, eligible retry work with `attempt_count>0`, and terminal work are immutable historical evidence. When their semantic bindings diverge, including a non-current active `follow_source` binding when that capability is advertised, they are returned as `protected_stale_work_instance_ids`; they are not retained as authorization. Attempt-start freshness MUST still reject any nonterminal protected row against changed truth.

For one response, `cancelled_work_instance_ids`, `retained_work_instance_ids`, `protected_stale_work_instance_ids`, and `created_work_instance_ids` are pairwise disjoint. Every existing row selected by reconciliation is classified as exactly cancelled, retained, or protected stale; a row created by the same command appears only in the created array.

`materialization.mode=none` performs mandatory cancellation but creates no replacement opportunity or work. `mode=bounded` uses the exact range, local-to-UTC normalization, completeness, limit, provenance, opportunity, and work rules from `schedule.create`, evaluated against successor truth. It reconciles the complete affected eligible set before creating the complete selected replacement set. A limit that would produce a prefix fails the whole command.

Occurrence provenance is regenerated when recurrence truth, primary scheduled time, or recurrence-bound policy targeting changes, and whenever bounded materialization needs a source range not already proven current. Unresolved or non-actionable provenance fails the transaction.

A primary-location-only truth change neither regenerates occurrence provenance nor
cancels otherwise-current notification work. Location is not part of the Version 1
recurrence, opportunity, work, route, or delivery freshness preimages.

### 5.6 Effects, Versioning, and Response

The stored command-receipt effect is closed over two booleans, `truth_changed` and `work_changed`:

| Truth | Work | Effect |
|---|---|---|
| true | true | `schedule_updated_and_reconciled` |
| true | false | `schedule_updated` |
| false | true | `schedule_reconciled` |
| false | false | `schedule_update_noop` |

Truth change creates exactly one next item version and one composite audit. Work-only reconciliation creates no item version but writes one composite audit. A complete no-op writes no item version or audit but still writes one replay receipt. Dry run returns deterministic would-be results and writes nothing.

The response returns target and current versions, closed effect, `truth_changed`, `work_changed`, canonically ordered `changed_dimensions`, current scheduled-time resolution, optional recurrence summary, current active policy mapping, disabled intent IDs, work reconciliation arrays, materialization summary, phase states, audit ID when written, and receipt summary. Base `changed_dimensions` values are `item`, `scheduled_time`, `recurrence`, `delivery`, and `reminders`. The advertised primary-location capability inserts `primary_location` after `item` and returns the conditional `primary_location_change` result defined by `specs/schedule-primary-location.md`.

Compatible replay returns top-level `effect=schedule_update_replay` plus the stored receipt effect under `receipt.effect`; it creates no row and does not re-resolve timezone data, context defaults, provenance, opportunities, or work.

## 6. `schedule.cancel`

### 6.1 Request and Transition

`schedule.cancel` is the type-neutral terminal operator command for a scheduled event or task. The closed request requires:

- `contract_version=spine.schedule-cancel.v1`;
- `command_id`, `actor_subject_id`, `item_id`, and exact `target_version`;
- `cancelled_at_utc`; and
- optional non-empty `reason_code`.

The target shell MUST be active. An event MUST currently be `scheduled`; a task MUST currently be `open`. Fresh invocation against another terminal detail state fails with `invalid_state_transition`; only compatible same-command replay is idempotent. Request `reason_code`, when present, is operator rationale persisted in the audit and receipt. It does not replace the canonical `parent_lifecycle_terminal` reason on reconciled work rows.

Fresh success creates exactly one next item version whose event or task detail status is `cancelled`, copies common and supporting truth forward under existing copy-forward rules, and leaves the shell active. It does not archive the item and does not rewrite recurrence history, policy intent status, completed work, or attempts. Parent terminal lifecycle alone makes every future opportunity non-actionable.

### 6.2 Reconciliation

In the same transaction, the command cancels every unstarted item-linked notification work row using `reason_code=parent_lifecycle_terminal`. The exact unstarted predicate is the Section 5.5 predicate. Started or terminal work remains immutable and is returned under `protected_stale_work_instance_ids`; it MUST fail any later attempt-start freshness check.

The command does not expand opportunities or materialize replacement work. It starts no work, invokes no adapter, and records no side-effect attempt.

Fresh success writes one composite `schedule_cancelled` audit and one `spine.schedule-cancel-receipt.v1` command receipt. The response returns the prior and resulting versions, terminal detail status, cancelled and protected work IDs, active policy and recurrence identities retained for history, phase states, audit identity, and receipt summary.

Compatible replay returns `effect=schedule_cancel_replay` while the nested receipt retains `effect=schedule_cancelled`. Replay creates no row and returns the original reconciliation evidence even if later workers or operators changed unrelated ledger state.

## 7. Atomicity, Validation, and Failure Ordering

`agenda.show` is read-only and uses this ordered validation/evaluation sequence:

A1. parse the closed request object and validate field shapes;
A2. verify ledger schema and the declared agenda contract family;
A3. decode an optional cursor and compare its bound request facts;
A4. resolve the view timezone and timezone-database directive;
A5. resolve both local boundaries and validate the normalized range;
A6. derive the current source snapshot and compare an optional cursor-bound snapshot;
A7. resolve stored source time facts, expand/select entries, and derive requested summaries and diagnostics; and
A8. construct the ordered response and verify response invariants.

It performs no write, creates no replay receipt, and fails before returning a partial page.

Each fresh write is one SQLite transaction and uses internal domain/persistence services rather than independently committing public handlers.

Shared validation order is:

1. parse a JSON object and reject unsupported fields;
2. validate command identifier, contract version, command ID, actor ID, item ID, target version, and action timestamp shapes;
3. resolve global command-ID collision and compatible same-command replay;
4. verify ledger schema and declared contract family;
5. resolve actor and target item;
6. validate target shell, type, detail lifecycle, and exact target-version freshness;
7. validate command-specific identity references and patch structure;
8. resolve timezone-data directives and delivery targets;
9. normalize complete successor truth and detect semantic conflicts;
10. derive reconciliation, provenance, opportunity, work, audit, and receipt results;
11. begin the atomic write, persist every selected effect, run commit invariants, and commit; and
12. read back receipt-bound evidence and fail closed if it disagrees.

Same-command replay and cross-command command-ID collision precede stale target-version checks. No other semantic validation may allow an incompatible stale request to mutate.

Any failure detected before a successful SQLite commit rolls back the complete command. There is no branch that keeps a truth mutation while losing required reconciliation, keeps cancelled work while losing replacement work, materializes a prefix, or writes a receipt for a rolled-back transaction. If Phase 12 detects contradictory evidence only after a successful commit, the command returns `runtime_failure` and preserves the committed command receipt as the authoritative replay index; it MUST NOT roll back selected rows independently or retry automatically under a new command ID.

### 7.1 Command-Specific Failure Matrix

The table below closes the Version 1 failures that depend on schedule-operation semantics rather than JSON Schema alone. `A` phase labels refer to the agenda sequence; numeric phases refer to the write-command sequence. When a row names two alternative fields, the implementation reports the first responsible field evaluated in the written order. Except for the explicitly post-commit Phase 12 branch above, every listed failure returns `ok=false`, persists no item, recurrence, policy, provenance, opportunity, work, audit, attempt, or command-receipt row, and leaves no partial mutation. The `error.message` is stable within an implementation release but is not a replay or compatibility fact.

| Command | Condition | Phase | `error.code` | `error.field` |
|---|---|---:|---|---|
| `agenda.show` | unknown view timezone | A4 | `invalid_request` | `timezone` |
| `agenda.show` | requested explicit or resolved `system_current` timezone-database version is unavailable | A4 | `environment_failure` | `timezone_database_version` |
| `agenda.show` | range start is nonexistent or ambiguous in the accepted view timezone | A5 | `invalid_request` | `range_start_local` |
| `agenda.show` | range end is nonexistent or ambiguous in the accepted view timezone | A5 | `invalid_request` | `range_end_local` |
| `agenda.show` | normalized range is empty, reversed, or longer than 366 elapsed days | A5 | `invalid_request` | `range_end_local` |
| `agenda.show` | cursor request facts differ from the cursor-bound query | A3 | `invalid_request` | `cursor` |
| `agenda.show` | a cursor-bound source snapshot has changed | A6 | `stale_cursor` | `cursor` |
| `agenda.show` | a selected stored source requires unavailable pinned timezone data | A7 | `environment_failure` | `primary_schedule.timezone_database_version` |
| `schedule.update` | target shell is archived | 6 | `invalid_state_transition` | `status` |
| `schedule.update` | resolved target item type is not `event` or `task` | 6 | `wrong_item_type` | `item_id` |
| `schedule.update` | target event/task detail is terminal | 6 | `invalid_state_transition` | `detail_status` |
| `schedule.update` | target version is not current | 6 | `stale_version` | `target_version` |
| `schedule.update` | primary event-start/task-due anchor is not `local_instant` | 7 | `invalid_request` | `primary_schedule.anchor_kind` |
| `schedule.update` | `patch.scheduled_time` targets an event with an end anchor | 7 | `invalid_request` | `patch.scheduled_time` |
| `schedule.update` | a recurring target changes `scheduled_time` without complete recurrence replacement | 7 | `missing_required_field` | `patch.recurrence` |
| `schedule.update` | advertised primary-location reference does not resolve | 7 | `referenced_row_not_found` | `patch.primary_location.location_id` |
| `schedule.update` | exactly one reminder intent/policy identity is supplied | 7 | `invalid_request` | the missing identity field under `patch.reminders[n]` |
| `schedule.update` | a policy key is rebound to a different current intent | 7 | `semantic_conflict` | `patch.reminders[n].policy_key` |
| `schedule.update` | two desired entries normalize to the same notification policy | 9 | `semantic_conflict` | `patch.reminders` |
| `schedule.update` | a new reminder has no inherited or supplied delivery route | 7 | `missing_required_field` | `patch.delivery` |
| `schedule.update` | delivery-target resolution fails | 8 | inherited exact code and field from `schedule.create` | inherited responsible `patch.delivery` field |
| `schedule.update` | successor recurrence, reminder, or materialization normalization fails | 9 | inherited exact code | inherited narrowest responsible `patch` or `materialization` field |
| `schedule.update` | required recurrence provenance cannot be resolved or regenerated | 10 | inherited exact provenance failure code | inherited recurrence-provenance field |
| `schedule.cancel` | target shell is archived | 6 | `invalid_state_transition` | `status` |
| `schedule.cancel` | resolved target item type is not `event` or `task` | 6 | `wrong_item_type` | `item_id` |
| `schedule.cancel` | event is not `scheduled` or task is not `open` | 6 | `invalid_state_transition` | `detail_status` |
| `schedule.cancel` | target version is not current | 6 | `stale_version` | `target_version` |
| either write command | schema/runtime does not support the declared contract family | 4 | `environment_failure` | the responsible schema or contract field |
| either write command | commit invariant fails before commit | 11 | `runtime_failure` | omitted unless one field is solely responsible |
| either write command | committed receipt-bound readback disagrees | 12 | `runtime_failure` | omitted unless one field is solely responsible |

Request-shape failures retain the common codes, fields, and CLI exits from `specs/agent-command-contract.md`. Within one phase, rows are evaluated in their table order for the applicable command except that exact narrow-field schema validation precedes stored-state semantic validation. Global command-ID collision and compatible same-command replay remain write Phase 3: compatible replay returns its stored success before target lifecycle, version, timezone, or patch semantic checks; incompatible same-command or cross-command reuse fails with `semantic_conflict`, `field=command_id`; neither branch creates a new domain row. Read-only `agenda.show` has no command receipt or replay branch.

## 8. Receipt and Replay Facts

Write receipts include canonical request semantic facts, their hash, normalization and receipt versions, target/result item versions, resolved timezone and route snapshots, prior and successor recurrence/policy identities, changed dimensions, work cancellation/retention/protection/creation arrays, materialization range and counts, phase states, audit identity when present, and the stored effect.

Arrays are canonically ordered:

- policy mappings by `policy_key`;
- intent IDs and work IDs lexically unless an opportunity order is explicitly returned;
- materialized opportunity/work pairs by eligibility time, opportunity ID, then work ID; and
- changed dimensions in the base fixed order `item`, `scheduled_time`, `recurrence`,
  `delivery`, `reminders`; when `spine.schedule-primary-location.v1` is advertised,
  the extended fixed order is `item`, `primary_location`, `scheduled_time`,
  `recurrence`, `delivery`, `reminders`.

Receipt evidence MUST be sufficient to reconstruct compatible replay without querying mutable route defaults, current timezone versions, current successor state, or a newly evaluated opportunity range. Missing or contradictory required historical evidence fails with `runtime_failure`; replay never repairs it.

## 9. Explicit Non-Goals

Version 1 does not define:

- recurrence removal, one-occurrence edits, or series splitting through `schedule.update`;
- event-duration shifting or event-end mutation;
- task completion through `schedule.cancel`;
- delivery, retry, adapter invocation, or approval;
- calendar/vendor projection reconciliation;
- dependency-aware agenda actionability, scoring, or planning recommendations;
- free-text intent parsing;
- unbounded agenda or materialization queries; or
- rollback of work or attempts that already crossed an execution boundary.

## 10. Acceptance Criteria

The contract is ready for implementation when schemas and structural fixtures prove its closed shapes and a bounded audit finds no identity, lifecycle, atomicity, or reconciliation ambiguity.

Implementation acceptance additionally requires executable proof that:

1. agenda local-day selection combines singleton and recurring event/task entries in exact order and invalidates its cursor after relevant source change;
2. agenda resolves each source with pinned timezone data and never silently substitutes unavailable versions;
3. a scheduled event can change time, reminder cadence, and route in one transaction while obsolete unstarted work is cancelled and bounded replacements are created;
4. a recurring scheduled-time change without complete recurrence replacement fails before mutation;
5. existing, changed, new, omitted, duplicate, and mismatched reminder-key branches are deterministic;
6. work-only reconciliation, truth-only update, combined update, and no-op branches produce their closed effects and version behavior;
7. injected failure after each logical phase rolls back truth, provenance, policy, work, audit, and receipt effects;
8. started and terminal work remains immutable while no longer authorizing a side effect under changed or terminal parent truth;
9. schedule cancellation atomically creates terminal item truth and cancels every unstarted notification work row;
10. compatible replay returns byte-equivalent receipt-bound identities without re-resolving environment state;
11. dry run produces the same would-be identities and persists nothing;
12. no command starts work, writes a side-effect attempt, invokes an adapter, or claims delivery; and
13. every composite result can be decomposed into canonical row identities and inspected through existing precision read surfaces, while every out-of-scope fine-grained mutation remains reachable through its owning lower-level command family.
