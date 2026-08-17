# Spine Notification Scheduling

Status: Draft v0.2.0; executable v1 contract family implemented
Scope: Canonical notification intent, bounded schedule expansion, durable work materialization, lifecycle reconciliation, and recurrence binding
Authority: Normative notification-scheduling target; runtime conformance requires matching persistence, command, fixture, and implementation declarations

Machine-readable contract family:

- `contracts/schemas/notification-types.schema.json`
- `contracts/schemas/notification-authoring.schema.json`
- `contracts/schemas/notification-policy.schema.json`
- `contracts/schemas/notification-command.schema.json`
- `contracts/schemas/notification-opportunity-response.schema.json`
- `contracts/notification-fixture-manifest.json`
- `contracts/vector-manifest.json`

## 1. Purpose

Spine notification scheduling represents durable intent to notify a recipient at one or more times derived from coordination truth. A notification policy is canonical Spine truth. A messenger, calendar, daemon, adapter, or runtime query is not.

This contract supports one-time notifications, explicit sets of target-relative notifications, and bounded repeated notifications. It applies to event starts and task due times, including each occurrence or one selected occurrence of a recurring item. It does not turn a notification into a coordination item, create a second schedule authority, or create a second adapter-attempt ledger.

## 2. Authority, Boundaries, and Version Constants

`notification_policies` owns recipient, delivery-target, target-binding, and schedule intent. Spine owns deterministic notification-opportunity expansion, work eligibility, reconciliation, and audit/replay facts. `work_instances` owns durable reminder work. `side_effect_attempts` remains the only adapter-result/send ledger.

`specs/schedule-create.md` owns only the composite transaction and high-level request/receipt mapping for initial item-plus-policy authoring. It does not define alternate notification schedules, opportunities, work identities, reconciliation, or delivery semantics.

Tickerd may request bounded expansion or materialization and may select eligible work. It MUST NOT own notification cadence, infer unstored schedule defaults, or deliver directly from a policy. An adapter MUST NOT run until a corresponding work instance exists and a side-effect attempt has been persisted.

Normative constants are:

- `contract_version=spine.notification-schedule.contract.v1`
- `normalization_version=spine.notification-schedule.normalization.v1`
- `canonical_json_version=spine.canonical-json.v1`
- authoring contract `spine.notification-schedule-authoring.v1`
- opportunity response contract `spine.notification-opportunities.v1`

`spine.canonical-json.v1` has exactly the meaning defined by `specs/ontology.md` and referenced by `specs/recurrence.md`. Every generated notification intent id, policy id, schedule hash, slot key, opportunity id, cursor digest, materialization receipt comparison, and reconciliation identity preimage MUST include `canonical_json_version`.

Notification schedules are first-class policy facts. Calendar cadence reuses the selector and timezone-resolution semantics of `specs/recurrence.md`; it does not create a recurrence set, recurrence revision, recurrence segment, or virtual coordination-item occurrence.

## 3. Canonical Notification Policy

A canonical version-scoped notification policy has required fields:

- `notification_intent_id`: stable logical identity carried across unchanged item-version copy-forward and policy edits.
- `notification_policy_id`: immutable row identity for this item version; it is the public alias of the ontology `policy_id`.
- `notification_schedule_id`: immutable normalized schedule-row identity for this policy version; it is the public alias of the ontology `schedule_id`.
- `item_id` and decimal-string `item_version`.
- decimal-string `intent_created_item_version` and `intent_created_by_command_id`, carried unchanged for the life of the intent.
- exactly one recipient owner selected by `recipient_kind=subject|subject_group` and its matching id.
- `channel` and `delivery_target_id`.
- `target` using Section 4.
- normalized `schedule` using Section 5.
- `normalized_notification_schedule_hash`.
- `late_handling` using Section 6.
- `status=active|disabled`.
- `created_at_utc` and `created_by_command_id`.

Optional lineage fields are `source_notification_policy_id` and `disabled_at_utc`. `source_notification_policy_id` is required when a new version-scoped row copies or edits an existing intent. `disabled_at_utc` is required exactly when `status=disabled`.

The complete current notification-policy set is materialized for each item version under the ontology's supporting-set rule. Copy-forward preserves `notification_intent_id`, normalized semantic fields, and schedule hash, derives a new `notification_policy_id`, and records the prior policy row as `source_notification_policy_id`. Policy rows are immutable semantic facts. Disabling or editing a policy creates the next item version and a successor policy row; it never updates a prior row in place.

Initial authoring derives `notification_intent_id` with prefix `notification_intent` over Spine canonical JSON containing exactly `derivation_version=spine.notification-intent-id.v1`, the three version constants, `item_id`, `intent_created_item_version`, and `intent_created_by_command_id`. A copied or edited row carries the id and both creation facts unchanged. A fresh second policy, even with byte-identical semantics, receives a different intent id unless duplicate-safe authoring resolves the existing intent.

`normalized_notification_schedule_hash` is the lowercase SHA-256 digest of Spine canonical JSON containing exactly `derivation_version=spine.normalized-notification-schedule-hash.v1`, the three version constants, normalized `target`, normalized `schedule`, and normalized `late_handling`. Notification intent, recipient, and delivery routing are policy facts but are not timing semantics and do not enter this hash. Two distinct intents may therefore have the same schedule hash without sharing opportunity or work identity. For `selected_occurrence`, normalized `target` contains the revision-independent `target_occurrence_selector` and omits the current `target_occurrence_key`; the key remains public resolution evidence and never makes a schedule hash revision-dependent.

`notification_schedule_id` uses prefix `notification_schedule` over Spine canonical JSON containing exactly `derivation_version=spine.notification-schedule-id.v1`, the three version constants, `notification_intent_id`, `item_id`, `item_version`, and `normalized_notification_schedule_hash`.

`notification_policy_id` uses prefix `notification_policy` over Spine canonical JSON containing exactly `derivation_version=spine.notification-policy-id.v1`, the three version constants, `notification_intent_id`, `intent_created_item_version`, `intent_created_by_command_id`, `item_id`, `item_version`, `notification_schedule_id`, recipient facts, `channel`, `delivery_target_id`, normalized target, `normalized_notification_schedule_hash`, `status`, `created_at_utc`, `created_by_command_id`, and optional `source_notification_policy_id` and `disabled_at_utc`. Derivation order is intent id, normalized schedule hash, schedule id, then policy id.

## 4. Target Binding

`target` contains required `anchor_role` and `application_scope`.

- `anchor_role` is `event_start` for an event or `task_due` for a task. It MUST match the target item type and MUST resolve to the current canonical anchor.
- `application_scope=item` applies once to a non-recurring target anchor and forbids occurrence fields.
- `application_scope=each_occurrence` applies the schedule independently to every actionable occurrence of a recurrence-bearing target anchor and forbids a selected occurrence key.
- `application_scope=selected_occurrence` applies only to one original scheduled occurrence and requires `target_occurrence_key`.

`item` is invalid when the target anchor carries recurrence. `each_occurrence` and `selected_occurrence` are invalid when it does not. A selected occurrence key is resolved at authoring to the current revision-independent `target_occurrence_selector`; both facts are persisted. Ambiguous, excluded, cancelled, or non-actionable selected occurrences fail with `semantic_conflict`, `field=target.target_occurrence_key`.

Normalized target facts are `anchor_role` and `application_scope`, plus `target_occurrence_selector` exactly for `selected_occurrence`. Current `target_occurrence_key` is resolution evidence, not a schedule-hash, slot-key, or opportunity-id preimage fact.

For `application_scope=each_occurrence`, every `once` boundary and both `repeat_window` boundaries MUST be target-relative. An absolute UTC boundary would repeat one global boundary across every target occurrence and is rejected with `invalid_request` on the responsible schedule field. `selected_occurrence` and non-recurring `item` scopes may use absolute boundaries.

For recurrence-bound expansion and materialization, every selected target occurrence MUST have active occurrence provenance satisfying `specs/recurrence.md`. The notification opportunity persists both the recurrence occurrence facts and `occurrence_provenance_id`. A policy cannot authorize work from a virtual occurrence alone.

## 5. Schedule Forms and Normalization

Every schedule has exactly one `kind`: `once`, `offsets`, or `repeat_window`. Request order is not semantic unless explicitly stated.

### 5.1 Boundary expressions

A boundary expression is exactly one of:

- `absolute_utc`: required `at_utc`.
- `target_offset` with `offset_basis=elapsed`: required signed canonical decimal-string `offset_seconds` in `-315576000..315576000`. Negative values are before the target and positive values are after it. The target must resolve to an instant.
- `target_offset` with `offset_basis=calendar_days`: required signed canonical decimal-string `offset_days` in `-3660..3660` and required `local_time`. `timezone` and `timezone_database_version` are inherited from a local target; an `instant_utc` target requires them explicitly. Calendar-day arithmetic operates on the target's local date before timezone resolution.

`absolute_utc` is already resolved and never carries timezone fields. Elapsed offsets add exact SI seconds to a resolved target instant. Calendar-day offsets preserve the requested local clock time across UTC-offset changes. For a nonexistent local result, the candidate is omitted; for an ambiguous result, the earlier UTC instant is selected. These are the same DST rules as recurrence expansion.

### 5.2 `once`

`once` contains exactly one required `at` boundary. It produces at most one schedule slot for each selected target.

### 5.3 `offsets`

`offsets` contains a non-empty `at` array of target-offset boundaries. Absolute boundaries are forbidden because they would repeat the same global instant for every occurrence. Boundaries normalize by their Spine canonical JSON bytes; byte-identical offsets collapse before slot derivation.

### 5.4 `repeat_window`

`repeat_window` contains required `start`, `stop`, `stop_inclusive`, and `cadence`. Both boundaries are resolved for each selected target. The resolved start MUST be earlier than the resolved stop, or equal only when `stop_inclusive=true`. A repeat window is always bounded; unbounded notification repetition is forbidden.

`cadence.kind=fixed_elapsed` requires canonical decimal-string `interval_seconds` in `1..31557600`. Its first candidate is the resolved start, and later candidates add exact SI seconds. `stop_inclusive=false` retains candidates strictly before the stop; `true` also retains an equal candidate.

`cadence.kind=local_calendar` requires `frequency`, optional `interval`, `seed_local_date`, `local_time`, `timezone`, and `timezone_database_version`; it permits the recurrence selector fields `by_month`, `by_month_day`, `by_weekday`, `by_set_position`, and `week_start`. `frequency`, selector legality, ordering, defaults, interval-period alignment, invalid-date omission, and DST resolution are exactly those of `specs/recurrence.md` Sections 3 and 6. Omitted `interval` derives `"1"`. Candidate production uses the cadence seed for phase, filters to the resolved repeat window, and never creates a recurrence set.

An elapsed cadence is appropriate for “every hour.” A local-calendar cadence is required for “every day at 08:00” when the wall-clock time must survive DST transitions. The normalized contract never interprets the phrase “every day” without an explicit `local_time`, timezone, timezone-database version, seed date, start boundary, and stop boundary. A conversational surface may resolve defaults, but it MUST persist and return the exact accepted facts.

### 5.5 Canonical examples

“Every hour for the six hours before the event” normalizes to an elapsed repeat window starting at target offset `-21600`, stopping at target offset `0`, with `interval_seconds="3600"` and `stop_inclusive=false`. It produces offsets -6h, -5h, -4h, -3h, -2h, and -1h.

“Every day at 08:00 until the event” normalizes to a local-calendar daily cadence with an explicit absolute or target-relative start, a target-relative stop, and `stop_inclusive=false`. It does not imply a hidden start date, clock time, or timezone.

## 6. Late Handling, Density, and Bounded Evaluation

Every policy requires exactly one late-handling rule:

- `{"kind":"skip"}`: a candidate earlier than `evaluated_at_utc` does not produce new work.
- `{"kind":"deliver_within","grace_seconds":"N"}`: a past candidate may produce work only when it is no more than `N` seconds late. The work retains its nominal `eligible_at_utc`; it is immediately eligible when materialized.

Late handling never changes opportunity identity or rewrites nominal eligibility. Adapter retry timing is controlled by the existing work/attempt lifecycle, not by notification cadence.

Every opportunity read uses explicit `evaluated_at_utc`; materialization uses `materialized_at_utc` as its evaluation instant. Every request also uses inclusive `range_start_utc`, exclusive `range_end_utc`, and a decimal-string `limit` in `1..1000`. The range MUST be no longer than 366 elapsed days. Candidate evaluation stops once the limit-plus-one ordering decision is known. Exceeding the range or limit fails with `invalid_request` on the responsible field. A conforming implementation MUST NOT enumerate an unbounded target stream to answer a bounded request.

For `each_occurrence`, the producer derives the bounded target-occurrence lookback and lookahead needed for the schedule's maximum negative and positive offsets, then requests recurrence occurrences for only that expanded source range. If the source range cannot be derived exactly, expansion and materialization fail closed; no work is written.

## 7. Notification Opportunities

A notification opportunity is virtual scheduling output, not work and not proof of delivery. It contains:

- `notification_opportunity_id` and `notification_schedule_slot_key`.
- notification intent and current policy identities, item/current/source version facts, and schedule hash.
- target anchor role, application scope, canonical target scheduled fact, and resolved target UTC instant when one exists.
- nominal `eligible_at_utc`.
- recipient, channel, and delivery-target facts.
- lifecycle and `actionable`.
- recurrence occurrence and provenance facts when recurrence-bound.

`notification_schedule_slot_key` uses prefix `notification_schedule_slot` over Spine canonical JSON containing exactly `derivation_version=spine.notification-schedule-slot-key.v1`, the three version constants, normalized schedule kind, and the slot's canonical semantic descriptor: the normalized `at` boundary for `once`; the normalized target-offset boundary for `offsets`; or the normalized cadence facts plus canonical candidate scheduled fact for `repeat_window`.

`notification_opportunity_id` uses prefix `notification_opportunity` over Spine canonical JSON containing exactly `derivation_version=spine.notification-opportunity-id.v1`, the three version constants, `notification_intent_id`, `normalized_notification_schedule_hash`, target binding facts, target occurrence selector or canonical item target fact, `notification_schedule_slot_key`, and nominal `eligible_at_utc`.

Opportunities order by `eligible_at_utc`, then `notification_opportunity_id`. Cross-policy opportunities never collapse. Duplicate slots inside one normalized policy and target collapse before identity derivation.

`actionable=true` exactly when the current policy is active, the item shell is active, the current event is scheduled or current task is open, the target occurrence is actionable when recurrence-bound, routing resolves to an active matching delivery target, and no schedule reconciliation conflict exists. Otherwise it is false and `reason_code` identifies the first failed predicate in this order. Closed opportunity reason codes are `notification_policy_disabled`, `item_inactive`, `event_not_scheduled`, `task_not_open`, `occurrence_non_actionable`, `delivery_target_unavailable`, and `notification_schedule_conflict`. An archived item shell returns `lifecycle=archived` and `reason_code=item_inactive`; the reason code names the failed actionability predicate and is not a shell-status value. Non-actionable opportunities MUST NOT materialize work.

## 8. Opportunity Read and Cursor Contract

`notification.opportunities` requires `item_id`, `evaluated_at_utc`, optional `notification_intent_id`, `range_start_utc`, `range_end_utc`, `limit`, and optional `cursor` and `include_diagnostics`. It does not mutate. When `include_diagnostics` is omitted or false, the required response `diagnostics` array is empty. When `include_diagnostics=true`, diagnostics are emitted under the rules below. This option changes only explanatory output; it does not change opportunity selection, identity, ordering, cursor construction, actionability, or failure outcomes.

A successful response uses `response_contract=spine.notification-opportunities.v1` and returns current item facts, accepted `evaluated_at_utc`, range, and limit, ordered `opportunities`, `has_more`, nullable `next_cursor`, and ordered `diagnostics`. A cursor binds the command, item id/current version, evaluated time, optional intent id, exact range, schedule contract and normalization versions, every selected current policy id and schedule hash, recurrence revision/hash facts when present, and the final ordering tuple. Any mismatch fails with `stale_cursor`, `field=cursor`.

Diagnostics order by severity, diagnostic code, field, optional eligible time, and optional source id. Diagnostics may report DST omission, late-slot skipping, or density truncation; they never change identity or authorization.

## 9. Durable Materialization

`notification_work.materialize` accepts a bounded opportunity range plus `command_id`, `actor_subject_id`, `item_id`, `target_version`, `materialized_at_utc`, optional `notification_intent_id`, and optional explicit `notification_opportunity_ids`. It runs the same expansion and freshness checks as `notification.opportunities`.

For every selected actionable opportunity without equivalent active work, materialization creates exactly one `work_instances` row with `work_kind=notification_reminder`, the current policy and item-version bindings, `notification_intent_id`, `notification_opportunity_id`, `normalized_notification_schedule_hash`, nominal `eligible_at_utc`, routing snapshot, recurrence occurrence/provenance facts when applicable, `status=eligible`, and zero attempts. The work id uses prefix `work_instance` over Spine canonical JSON containing exactly `derivation_version=spine.notification-work-instance-id.v1`, the three version constants, `notification_opportunity_id`, and `delivery_target_id`. Overlapping materialization ranges retain equivalent work and create no duplicates.

Materialization is atomic for its selected set. Closed effects are:

- `notification_work_created`: at least one work row created and none cancelled by reconciliation.
- `notification_work_reconciled`: at least one row created or retained and at least one stale eligible row cancelled with a Section 10 reason code.
- `notification_work_all_retained`: one or more opportunities selected and every equivalent work row retained.
- `notification_work_zero_selected`: no actionable opportunity selected and no row changed.

The response reports ordered `created_work_instance_ids`, `retained_work_instance_ids`, and `cancelled_work_instance_ids`; arrays are empty when the effect says they are. Effect precedence is reconciled, created, all-retained, zero-selected.

Materialization creates no side-effect attempt and invokes no adapter. Same-command compatible replay returns the stored receipt and identities without mutation. Incompatible command-id reuse fails before freshness checks.

## 10. Reconciliation and Lifecycle

Schedule-generated work carries enough provenance to revalidate its notification intent, current policy semantics, item target, recurrence occurrence when present, and routing before processing.

A schedule edit, target reschedule, target recurrence revision, selected-occurrence lifecycle change, delivery-target change, policy disablement, or terminal item transition can make eligible work stale or non-actionable. Reconciliation MUST prevent adapter invocation and MUST cancel only unstarted work. The base executable-v1 closed cancellation reason codes are `notification_schedule_superseded`, `notification_target_changed`, `notification_occurrence_stale`, `notification_routing_changed`, `notification_policy_disabled`, and `parent_lifecycle_terminal`; the first applicable reason in this order is persisted. In-progress and terminal work remain immutable historical facts and receive audit/report facts when later truth diverges.

`specs/relative-temporal-bindings.md` defines a conditional extension owned by this notification contract. A runtime advertising `spine.relative-temporal-binding.v1` MUST use this extended closed precedence instead: `notification_schedule_superseded`, `notification_target_changed`, `notification_occurrence_stale`, `notification_temporal_binding_stale`, `notification_routing_changed`, `notification_policy_disabled`, then `parent_lifecycle_terminal`. `notification_temporal_binding_stale` is legal only for notification work targeting a task due anchor governed by an active `follow_source` binding whose computed binding state is not `current`. Schema 8 implements the complete family atomically across creation, discovery, reconciliation, readback, persistence, machine contracts, and attempt-start enforcement. A runtime that does not advertise that family continues to use the six-value base list.

An unchanged policy copy-forward with the same `notification_intent_id`, schedule hash, target facts, and routing MAY retain existing eligible work by opportunity identity even though the version-scoped `notification_policy_id` changed. A changed semantic fact MUST NOT retain the work merely because its `eligible_at_utc` is equal.

Disabling a policy prevents all future opportunity actionability and all unstarted work for that intent. Cancelling or archiving an item, cancelling an event, or completing/cancelling a task does the same. Re-enabling a disabled intent is not defined in v1; create a new intent or use a future explicit command.

## 11. Delivery and Retry Boundary

Each notification opportunity represents one intended reminder. Each materialized work instance represents the durable execution of that one reminder. Multiple hourly reminders are multiple opportunities and multiple work instances.

A delivery retry is not another scheduled reminder. Retries remain attempts or retry state under the same work instance. They MUST preserve the original `notification_opportunity_id`, nominal eligibility, and idempotency basis. A scheduler MUST NOT create another opportunity to retry a failed adapter call.

Before adapter invocation, processing rechecks policy, item, target, occurrence provenance, routing, and work lifecycle freshness; persists `side_effect_attempts`; and then invokes the adapter. Failure before invocation creates no started attempt unless the existing side-effect contract explicitly requires a rejected attempt fact.

When `spine.relative-temporal-binding.v1` is advertised, attempt start performs one additional authoritative lookup for notification work targeting the task's current `task_due` anchor. If that anchor has an active `follow_source` binding, processing MUST compute the binding state from current canonical source, target, revision, selector/provenance, binding, and `part_of` relation facts exactly as specified by `specs/relative-temporal-bindings.md`. Adapter invocation is permitted only when that state is exactly `current` and the current task due anchor remains semantically equal to the latest binding revision's target anchor. Any other state fails closed before a `side_effect_attempts` row with `attempt_status=started` is persisted. An eligible row is then cancellable as `notification_temporal_binding_stale` only when it also satisfies the owning reconciliation workflow's unstarted predicate and no earlier cancellation reason applies; protected retry, in-progress, and terminal rows remain evidence and do not regain authorization. Snapshot and retired bindings do not add this freshness gate.

## 12. Commands and Validation Order

The structured family adds or extends these commands:

- `reminder.create`: create a notification intent and first policy row from `spine.notification-schedule-authoring.v1` without performing an external send.
- `reminder.edit`: create the next item version and successor policy row for one intent.
- `reminder.disable`: create the next item version and disabled successor policy row.
- `notification.opportunities`: read bounded virtual opportunities.
- `notification_work.materialize`: persist bounded durable work.

Fresh write validation order is: envelope shape; command-id collision/replay lookup; scalar and enum syntax; actor; item and recipient references; delivery-target binding; target anchor and application scope; target-version freshness; schedule shape and normalization; target/occurrence resolution; recurrence provenance when needed; lifecycle; duplicate/no-op comparison; identity derivation; atomic persistence. Command-specific failures MUST NOT reorder these phases.

`reminder.create` returns intent, policy, item-version, schedule-hash, audit, and receipt identities and never eagerly creates work. Structured duplicate-safe identity is current active `item_id`, recipient-owner facts, `channel`, `delivery_target_id`, and `normalized_notification_schedule_hash`; that hash already binds normalized target, schedule, and late handling. With `if_absent=true`, a byte-equivalent current intent returns `effect=reminder_duplicate_noop`, creates only a command receipt, and returns the existing intent/policy/schedule identities; without it, the duplicate fails with `semantic_conflict`, `field=notification`. `reminder.edit` has effects `reminder_updated` and `reminder_edit_noop`. `reminder.disable` has effects `reminder_disabled` and `reminder_disable_noop`.

`schedule.create` is the only version-1 composite authoring contract currently specified to create initial policies and optionally perform bounded Section 9 materialization in the same transaction as a new item. It derives `application_scope=item` for non-recurring schedules and `application_scope=each_occurrence` for recurring schedules, sorts request policies by their request-local keys, uses the same notification identities and normalized schedules as this specification, and creates no synthetic lower-level command receipts. Its recurring bounded branch MUST establish current occurrence provenance before opportunity expansion. It does not alter `reminder.create`, opportunity, materialization, work, reconciliation, or delivery semantics.

## 13. Conformance Vectors

A conforming implementation publishes canonical input, normalized output, exact preimage bytes, lowercase SHA-256 digests, expansion output, and expected failures for at least:

- one notification six hours before an instant target;
- explicit offsets with duplicate collapse and request-order independence;
- every hour for six hours before, exclusive stop;
- every hour for six hours before, inclusive stop;
- every day at 08:00 local through a DST transition;
- nonexistent and ambiguous local reminder times;
- calendar cadence selector defaults and ordering;
- item, each-occurrence, and selected-occurrence scopes;
- recurring-item occurrence provenance freshness and stale failure;
- overlapping materialization ranges and all four materialization effects;
- skip and deliver-within late handling;
- unchanged policy copy-forward retention;
- schedule edit, reschedule, disable, cancellation, completion, and archive suppression;
- distinction between repeated opportunities and delivery retries;
- cursor replay and invalidation;
- dry run, same-command replay, incompatible replay, and stale target version.

The computed vector corpus is indexed by `contracts/vector-manifest.json`. Each vector publishes canonical input, normalized output, exact canonical JSON preimage text, digest or generated identity, and observable expansion facts. Structural contract fixtures remain shape examples and never override a computed vector or this specification.

## 14. Acceptance Criteria

1. Two implementations given the same normalized policy and bounded source facts produce byte-identical schedule hashes, slot keys, opportunity ids, ordering, and cursor facts.
2. “Every hour for six hours before” produces exactly six opportunities under an exclusive stop.
3. A daily local reminder preserves its wall-clock time through DST while applying the defined omission and ambiguity rules.
4. No unbounded request, hidden default, second schedule store, hidden scheduler row, or direct policy-to-adapter delivery is possible.
5. A recurring-item reminder cannot materialize without current occurrence provenance.
6. Overlapping materialization is idempotent and cannot create duplicate work.
7. A delivery retry cannot be mistaken for a new scheduled reminder.
8. Policy, target, recurrence, routing, and lifecycle changes fail closed before external invocation.
9. Every external send remains represented by `side_effect_attempts` and no notification-specific attempt ledger exists.
