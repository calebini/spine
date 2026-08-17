# Spine Relative Temporal Bindings and Atomic Related-Task Creation

Status: Draft v0.1; not implemented and not advertised by the runtime
Scope: Explicit cross-item temporal derivation plus one atomic operator command for creating a task that is part of an existing event
Created: 2026-08-17

## 1. Purpose

Spine can atomically create one scheduled item with reminders, and it can independently relate two existing items. It does not yet have a canonical answer for the operator intent:

> Create a task that is part of this event, give it a due time relative to that event, and remind me about it.

That intent currently requires callers to copy the event time into a task request, submit separate schedule and relation commands, and decide what should happen when the event later moves. The choreography is cumbersome, and copied time is semantically incomplete because it does not say whether the task should remain fixed or follow the event.

This specification introduces two additive capabilities:

1. a first-class **relative temporal binding**, which records why one item anchor was derived from another item anchor and whether it follows later source changes; and
2. `schedule.related_task.create`, one atomic operator-facing command that creates an ordinary task, an ordinary `part_of` relation, the explicit binding and resolved task-due anchor, optional reminder policies, optional bounded work, one audit, and one deterministic receipt.

The composite is a convenience boundary over granular canonical facts. It is not a new item type, schedule container, relation type, notification model, recurrence engine, or delivery path.

## 2. Foundational Invariants

The following invariants are normative for this draft and should survive contract sharpening:

1. **Structure does not imply time.** An active `part_of` relation never, by itself, causes time inheritance, rescheduling, reminder creation, or cancellation.
2. **Time inheritance is explicit.** Cross-item temporal behavior exists only when an active relative temporal binding names the source, target, offset, and binding mode.
3. **Resolved anchors remain canonical.** Every task version governed or produced by a binding owns an ordinary immutable `task_due` temporal anchor. Reads, recurrence, reminders, agenda projection, and adapters continue to consume that concrete anchor.
4. **No invisible item mutation.** Following a moved source creates a new target item version and a new binding revision in one reconciliation transaction. A read-time join MUST NOT make an old task version appear to have a different due time.
5. **Granularity is preserved.** Items, versions, anchors, relations, bindings, policies, opportunities, work, attempts, audits, and receipts retain independent identities and remain available through their lower-level read surfaces.
6. **Composite atomicity does not collapse evidence.** One composite receipt enumerates all created identities; it does not manufacture successful lower-level command receipts.
7. **Stale derived time cannot authorize delivery.** Work targeting an active `follow_source` binding MUST pass binding freshness at attempt start. A stale or unresolved binding prevents an external side effect until reconciliation succeeds.
8. **Authored is not delivered.** The stable lifecycle language in `specs/schedule-operator-tools.md` applies unchanged.
9. **Natural-language interpretation stays outside this contract.** An agent may translate “task attached to that event” into this normalized request, but Spine accepts only explicit identifiers and structured facts.
10. **Channel rendering stays outside this contract.** A WhatsApp-sized acknowledgement is a deterministic projection of the receipt, not a new canonical receipt or lifecycle model.

## 3. Authority and Proposed Version Family

This draft depends on:

- `specs/ontology.md` for coordination items, versions, temporal anchors, relations, policies, work, audits, and receipts;
- `specs/recurrence.md` for selected-occurrence identity, selectors, expansion, and provenance;
- `specs/notifications.md` for policy normalization, opportunities, work materialization, reconciliation, and attempt-start freshness;
- `specs/schedule-create.md` for atomic initial schedule authoring and materialization semantics;
- `specs/schedule-operations.md` for whole-schedule mutation and stale-work classification; and
- `specs/agent-command-contract.md` for command identity, replay, dry-run, validation, error, and transport rules.

The proposed Version 1 constants are:

- `binding_contract=spine.relative-temporal-binding.v1`;
- `binding_normalization_version=spine.relative-temporal-binding-normalization.v1`;
- `contract_version=spine.schedule-related-task-create.v1`;
- `response_contract=spine.schedule-related-task-create-response.v1`;
- `receipt_contract=spine.schedule-related-task-create-receipt.v1`; and
- `canonical_json_version=spine.canonical-json.v1`.

These names are design inputs, not runtime claims. No implementation may advertise them until matching migrations, schemas, fixtures, behavioral tests, and command handling exist.

## 4. Version 1 Boundary

Version 1 supports:

- creating exactly one new open task;
- one existing active scheduled event as the source;
- either a non-recurring event start or one selected current actionable occurrence of a recurring event;
- one stored `part_of` relation from the new task to the source event;
- one binding from source `event_start` to target `task_due`;
- an exact signed elapsed-seconds offset;
- explicit `snapshot` or `follow_source` behavior;
- zero through 32 task reminder policies targeting the resolved task due time;
- optional bounded reminder opportunity expansion and work materialization; and
- deterministic dry run, commit, replay, readback, and failure evidence.

Version 1 does not support:

- treating `part_of`, `depends_on`, `contains`, or `blocks` as a temporal instruction;
- binding an existing target item through the composite;
- creating one task per occurrence of a recurring event;
- source roles other than event start or target roles other than task due;
- event-end, task-defer, date-only, window, or floating-time bindings;
- calendar-day or business-day offset arithmetic;
- a target recurrence derived from a source recurrence;
- direct notification policies whose target anchor belongs to another item;
- unbounded materialization, delivery, adapter invocation, or side-effect attempts;
- free-text entity resolution; or
- synchronous fan-out mutation of every dependent task inside a source event update.

Calendar-relative arithmetic is a plausible later extension, but it requires an explicit timezone basis, invalid-local-time behavior, and timezone-database pinning contract. Version 1 uses elapsed seconds so a source UTC instant plus offset has exactly one result.

## 5. Relative Temporal Binding Model

### 5.1 Meaning

A relative temporal binding says:

> The target item's named anchor was resolved from the source item's named anchor or selected occurrence, using this exact offset and this exact update policy.

The binding is neither a relation alias nor a virtual temporal anchor. The target task still stores an ordinary concrete due anchor. The binding supplies provenance and, for `follow_source`, a deterministic obligation to reconcile when the source changes.

### 5.2 Logical header

One logical binding has these minimum header facts:

- `temporal_binding_id`;
- `binding_contract`;
- `target_item_id`;
- `target_anchor_role=task_due`;
- `source_item_id`;
- `source_anchor_role=event_start`;
- `binding_mode=snapshot|follow_source`;
- `source_terminal_behavior=cancel_target|detach_at_last_value|require_decision`, required exactly for `follow_source`;
- `created_by_command_id`;
- `created_by_subject_id`;
- `created_at_utc`; and
- `binding_status=active|retired`.

All header facts except `binding_status` are immutable. Status may transition only from `active` to `retired`; reactivation creates a new logical binding. `snapshot` omits `source_terminal_behavior` because later source lifecycle has no effect. `follow_source` requires an explicit value and has no ambient default.

At most one active logical temporal binding may govern `(target_item_id, target_anchor_role)`. A target may still have unrelated structural relations.

### 5.3 Immutable binding revisions

Every successful initial resolution or later reconciliation creates one immutable binding revision with:

- `temporal_binding_revision_id` and positive `revision_index`;
- `temporal_binding_id`;
- optional `source_temporal_binding_revision_id` for revisions after the first;
- `source_target_version`, the exact current source item version used;
- `source_scope=item|selected_occurrence`;
- source anchor identity and canonical source scheduled fact;
- for `selected_occurrence`, the current source recurrence revision, current occurrence key, revision-independent target occurrence selector, and current actionable occurrence-provenance identity;
- `offset_basis=elapsed` and signed decimal-string `offset_seconds`;
- resolved source UTC instant;
- resolved target UTC instant;
- target local date, local time, timezone, and concrete timezone-database version;
- `target_item_version` and `target_anchor_id`;
- `resolution_kind=initial|source_changed|detached|source_terminal`;
- normalized binding hash and every version constant used by its preimage;
- `created_by_command_id`; and
- `created_at_utc`.

The current revision is the greatest persisted revision index for an active logical binding. Revisions are never updated in place.

### 5.4 Source scopes

`source_scope=item` is legal only when the source event has no active recurrence set. It resolves the event's current concrete start anchor.

`source_scope=selected_occurrence` is required when the source event is recurring. The request supplies both:

- the current `target_occurrence_key`, which proves exactly which current occurrence the caller selected; and
- the revision-independent `target_occurrence_selector`, which allows the same semantic source to be resolved after a recurrence revision.

Initial authoring requires the key and selector to resolve to exactly one current actionable occurrence with active provenance for `consumer=temporal_binding`. That consumer value is an additive recurrence-provenance contract and schema change; it is not implemented today. Zero matches, multiple matches, stale recurrence facts, omitted occurrences, exclusions, or non-actionable provenance fail closed.

Version 1 does not interpret `source_scope=item` on a recurring event as “the next occurrence,” “every occurrence,” or the recurrence seed.

### 5.5 Offset and target expression

Version 1 computes:

`resolved_target_utc = resolved_source_utc + offset_seconds`

using exact elapsed SI seconds. The offset is a signed canonical decimal string within `-31622400..31622400`, an inclusive 366-day bound. `0` means the task is due at the selected event start.

The target due anchor is expressed as a `local_instant` in the source occurrence's timezone using the exact timezone-database version pinned by the source recurrence or concrete source anchor. The implementation MUST persist that concrete version in the binding revision, target anchor, receipt, and readback. The caller does not provide or recompute target local or UTC time.

Because elapsed arithmetic occurs after the source resolves to UTC, crossing a daylight-saving transition preserves elapsed duration rather than wall-clock time. A future calendar-relative basis must use another contract version or an explicitly extended closed union.

### 5.6 Snapshot mode

`binding_mode=snapshot` resolves the source once. Later source reschedule, recurrence edit, exclusion, cancellation, relation lifecycle change, or timezone-data installation does not move or cancel the task.

The binding remains durable derivation evidence. Readback reports whether the task's current due anchor still equals the resolved snapshot, but a later explicit task reschedule does not become stale merely because it diverges from the snapshot.

### 5.7 Follow-source mode and freshness

`binding_mode=follow_source` makes the latest binding revision the governing derivation for the target due anchor. It is `current` only when all of these hold:

- the source shell and event detail remain active and scheduled;
- the named source anchor or selected occurrence resolves exactly once;
- the current source item version and, when applicable, recurrence revision and selector result equal the revision's source facts;
- the target item remains open and its current version and due anchor equal the revision's target facts;
- the logical binding remains active; and
- the required `part_of` relation remains active.

Otherwise the binding is computed as `stale`, `source_terminal`, `source_unresolved`, `target_diverged`, or `relationship_inactive`. These states are read-model facts derived from current canonical rows; a source mutation does not rewrite an old binding revision merely to label it stale.

Any notification opportunity or work row targeting the bound task due time is non-actionable while the binding is not `current`. Attempt-start freshness MUST check this invariant even when the work row was valid when materialized.

### 5.8 Reconciliation posture

Following is implemented by a bounded reconciliation transaction, not a read-time illusion and not an unbounded cascade inside the source mutation.

A future `schedule.binding.reconcile` command will accept the logical binding ID, exact current binding revision, exact source and target versions, action time, and optional bounded reminder materialization. When the source still resolves and the derived target differs, one success MUST atomically:

1. create one next task version with a new concrete due anchor;
2. create one next binding revision pointing to that target version and anchor;
3. copy forward or reconcile unchanged task supporting truth;
4. classify stale notification work and optionally materialize bounded replacements;
5. write one audit and one command receipt; and
6. return the prior and successor source, target, binding, policy, and work evidence.

If the derived target is unchanged, reconciliation is a receipt-bearing no-op and creates no task version or binding revision.

If the source is terminal, the binding's explicit `source_terminal_behavior` controls reconciliation:

- `cancel_target` atomically cancels the open task and reconciles its unstarted notification work;
- `detach_at_last_value` retires the binding and leaves the task at its last concrete due anchor; or
- `require_decision` returns a structured unresolved result, keeps the task and binding unchanged, and leaves schedule-dependent work non-actionable.

The implementation plan must define how tickerd or an operator discovers stale bindings and invokes this bounded command. Discovery cadence is not canonical truth, but reconciliation results are.

Direct `schedule.update` replacement of a due anchor governed by an active `follow_source` binding MUST fail until a later accepted contract supplies an atomic detach-or-replace action. The implementation MUST NOT silently break or overwrite the binding.

## 6. `schedule.related_task.create`

### 6.1 Request

The proposed request is a closed JSON object with:

- `contract_version=spine.schedule-related-task-create.v1`;
- `command_id`;
- `actor_subject_id`;
- `created_at_utc`;
- `source`;
- `task`;
- `relationship`;
- `temporal_binding`;
- optional `delivery`;
- `reminders`; and
- `materialization`.

`source` contains:

- `item_id`;
- exact `target_version`;
- `anchor_role=event_start`;
- `scope=item|selected_occurrence`; and
- exactly for `selected_occurrence`, `source_recurrence_revision_id`, `target_occurrence_key`, and `target_occurrence_selector`.

`task` reuses the `schedule.create` task item shape: required `title`; optional `summary`, `source_ref`, `priority`, and complete initial `subject_roles`. It MUST NOT accept a due anchor or recurrence because the binding derives the due anchor and Version 1 does not derive target recurrence.

`relationship` is exactly `{ "relation_type": "part_of" }`. Its presence makes the requested structural fact explicit and leaves room for a later contract version without inferring a relationship from binding existence.

`temporal_binding` contains required `binding_mode`, `offset_basis=elapsed`, and signed decimal-string `offset_seconds`. `source_terminal_behavior` is required exactly when `binding_mode=follow_source` and forbidden for `snapshot`.

`reminders` contains zero through 32 `schedule.create` reminder entries. When non-empty, `delivery` is required and has the exact `schedule.create` route shape. When empty, `delivery` is forbidden. Every policy targets the new task's concrete `task_due` anchor with `application_scope=item`.

`materialization` has the exact `schedule.create` `none|bounded` union. `bounded` requires at least one reminder. Its `item_relative` range is relative to the derived task due instant, and its local range uses the derived task timezone and concrete timezone-database version.

### 6.2 Source validation

Fresh authoring requires:

- an existing active source shell with `item_type=event`;
- exact current `source.target_version`;
- current detail `event_status=scheduled`;
- a timed source that resolves to one UTC instant under available pinned timezone data;
- the scope/recurrence agreement from Section 5.4; and
- no source occurrence that is excluded, omitted, non-actionable, stale, or ambiguous.

The command does not accept a title fragment, ordinal such as “the golf trip,” or a relation query in place of `source.item_id`. Entity resolution is a caller responsibility and must happen before the normalized request is submitted.

### 6.3 Atomic persistence

One fresh non-dry-run success is one database transaction whose logical phases are:

1. validate the closed request and derive replay semantic facts;
2. resolve command-ID replay or collision;
3. verify schema, declared contracts, actor, and source version/lifecycle;
4. resolve the concrete source event start or selected occurrence;
5. normalize the binding, derive the target instant, and validate task, relation, route, reminders, and materialization;
6. create the task shell, common version `1`, task detail, and concrete due anchor;
7. create the active stored `part_of` relation from task to source event;
8. create the temporal-binding header and revision;
9. create the complete initial notification policy set;
10. expand and materialize the complete bounded selection when requested;
11. persist one composite audit and one composite command receipt;
12. run commit invariants and commit; and
13. read back receipt-bound evidence and fail closed on contradiction.

Any failure before commit rolls back every selected row. There is no branch that leaves a task without its requested relation or binding, a relation without its task, a partial reminder set, a partial materialization range, or a receipt for rolled-back work.

The composite uses internal domain and persistence services. It MUST NOT invoke `task.create`, `relation.create`, `reminder.create`, or `notification_work.materialize` as independently committing public subcommands and MUST NOT fabricate receipts for those commands.

### 6.4 Identity

Ordinary command-derived identities use `command=schedule.related_task.create`, the shared `spine.command-id.v1` derivation, and these request paths:

- task item: `/task`;
- due anchor: `/temporal_binding/resolved_target`;
- stored `part_of` relation: `/relationship`;
- logical temporal binding: `/temporal_binding`;
- initial binding revision: `/temporal_binding/revisions/0`;
- task subject roles: `/task/subject_roles/<canonical-index>`;
- composite audit: `/audit`; and
- command receipt: `/`.

Notification, opportunity, provenance, and work identities retain their owning specifications. The normalized binding hash is SHA-256 over Spine canonical JSON containing the version constants; source and target item/anchor roles; binding mode; conditionally present terminal behavior; source scope and selected-occurrence selector facts; source version, recurrence revision, scheduled fact, and resolved UTC instant; offset basis and seconds; target version, local schedule facts, resolved UTC instant, timezone, and concrete timezone-database version. Generated IDs, occurrence keys, provenance IDs, command IDs, actors, and creation/audit timestamps are not in this semantic hash.

The exact hash preimage and canonical ordering must be closed in the machine-contract phase before implementation begins.

### 6.5 Receipt and lifecycle

Fresh success stores `effect=related_task_schedule_created`. Compatible replay returns top-level `effect=related_task_schedule_create_replay` while the nested receipt retains the stored effect.

The response and receipt expose at least:

- task item ID, version, detail status, title, and subject roles;
- source event ID/version, source scope, source anchor or occurrence identities, resolved source local/UTC time, timezone, and timezone-database version;
- relation ID, direction, type, and status;
- temporal binding ID/revision, mode, terminal behavior, offset, resolution state, and normalized hash;
- target due-anchor ID and resolved local/UTC time;
- delivery snapshot when reminders exist;
- policy key, intent, schedule, and policy IDs;
- opportunity and work identities/counts and bounded range when evaluated;
- separate lifecycle facts for task authored, relation authored, binding resolved, policies authored, opportunities expanded, work materialized, and delivery attempt/outcome;
- audit ID and command-receipt ID; and
- `delivery_state=not_attempted_by_command`.

No success response may claim that the related task was delivered, sent, or acted upon.

### 6.6 Dry run and replay

Dry run performs complete source resolution, normalization, identity derivation, opportunity expansion, and would-be work classification against one read snapshot, then writes nothing. It returns explicit `dry_run=true` and preview lifecycle facts.

Replay follows the shared global command-ID ordering. A compatible same-command replay returns the original source, target, route, timezone-data, binding, policy, and work snapshot without resolving the source again. Later source movement, relation change, route change, or timezone-data installation MUST NOT alter replay output.

If receipt-bound historical evidence is missing or contradictory, replay fails with `runtime_failure`; it does not reconstruct different facts from current state.

## 7. Read and Mutation Surfaces

Implementation of this contract family requires additive readback:

- `schedule.show` can include `relations` and `temporal_bindings`, returning the current concrete schedule plus binding mode, current revision, freshness state, source summary, offset, and relation identity;
- `agenda.show` returns a compact binding summary and MUST distinguish a task that is open but whose follow-source schedule is stale;
- `relation.list` continues to return the ordinary stored `part_of` row and derived `contains` alias without temporal inference; and
- a bounded binding discovery/read command must support reconciliation without raw SQL.

A stale binding does not erase the task from canonical reads. It does make the derived due schedule and schedule-dependent notification work non-actionable until reconciliation or explicit resolution.

Later mutation design must close:

- `schedule.binding.reconcile` request, effects, and failure ordering;
- atomic detach or mode change;
- relation inactivation interaction;
- source terminal resolution;
- target completion or cancellation interaction; and
- whether source `schedule.update` receipts enumerate affected binding IDs or only expose them through bounded discovery.

The first runtime implementation MUST NOT claim full `follow_source` support until reconciliation, discovery/readback, and attempt-start freshness ship together.

## 8. Failure Posture

At minimum, machine contracts must distinguish:

| Condition | Code | Field |
|---|---|---|
| source item is not an event | `wrong_item_type` | `source.item_id` |
| source event or shell is terminal | `invalid_state_transition` | `source.item_id` |
| source target version is stale | `stale_version` | `source.target_version` |
| scope disagrees with recurrence state | `invalid_request` | `source.scope` |
| selected occurrence key/revision is stale | `stale_version` | narrowest source occurrence field |
| selected occurrence resolves zero or multiple times | `semantic_conflict` | `source.target_occurrence_selector` |
| source occurrence is not actionable | `semantic_conflict` | `source.target_occurrence_key` |
| pinned timezone data is unavailable | `environment_failure` | source timezone-database field |
| offset is outside the Version 1 bound | `invalid_request` | `temporal_binding.offset_seconds` |
| snapshot supplies terminal behavior | `invalid_request` | `temporal_binding.source_terminal_behavior` |
| reminders exist without delivery | `missing_required_field` | `delivery` |
| delivery exists without reminders | `invalid_request` | `delivery` |
| bounded materialization has no reminders | `invalid_request` | `materialization.mode` |
| relation or binding uniqueness conflicts | `semantic_conflict` | `relationship` or `temporal_binding` |
| commit/readback evidence disagrees | `runtime_failure` | omitted unless singular |

The detailed validation order, CLI exits, JSON Schema failures, and replay precedence must be closed before implementation. Compatible replay must precede current source lifecycle, version, occurrence, timezone, and route checks.

## 9. Initial Contract and Fixture Plan

Before runtime work, add:

- a shared relative-temporal-binding type schema;
- request, response, and failure schemas for `schedule.related_task.create`;
- request, response, and failure schemas for `schedule.binding.reconcile` if `follow_source` is in the first implementation slice;
- a fixture manifest and structural validator tests;
- computed identity vectors for task, relation, binding, revision, anchor, audit, receipt, and normalized binding hash; and
- behavioral transaction, replay, stale-source, recurrence, route, materialization, readback, and attempt-start freshness tests.

Minimum positive fixtures:

1. snapshot task at event start with no reminders;
2. snapshot task before event with one reminder and bounded work;
3. follow-source task at a non-recurring event;
4. task bound to one selected recurring occurrence;
5. compatible replay after the source later moves; and
6. dry run with deterministic would-be identities and no rows.

Minimum failure and reconciliation fixtures:

1. wrong source type;
2. stale source version;
3. recurring source with `scope=item`;
4. stale or excluded selected occurrence;
5. invalid offset;
6. missing or mismatched delivery target;
7. injected failures after task, relation, binding, policy, and work phases proving total rollback;
8. source move causing follow binding staleness and delivery ineligibility;
9. successful follow reconciliation producing one next task version;
10. follow-source terminal behavior for all three closed values; and
11. direct target schedule update rejected while follow binding governs it.

## 10. Acceptance Criteria

This contract family is ready to implement only when:

1. two independent implementations can derive byte-identical normalized binding hashes and command-derived IDs from the fixture corpus;
2. `part_of` without a binding demonstrably produces no temporal effect;
3. the composite either commits the complete task/relation/binding/reminder/work bundle or no selected row;
4. all granular child identities remain independently queryable;
5. snapshot and follow-source behavior differ exactly as specified after source movement;
6. a follow reconciliation creates an ordinary next task version and never mutates an old anchor or item version;
7. stale, unresolved, terminal, divergent, or relation-inactive follow bindings cannot authorize reminder delivery;
8. compatible replay returns original receipt facts without reevaluating current source or route state;
9. readback distinguishes open task lifecycle from binding freshness and notification delivery lifecycle;
10. no command performs delivery or creates a `side_effect_attempts` row; and
11. the operator guide can express success using stable lifecycle language without hiding the relation, binding mode, or stale state.

## 11. Audit Questions for the First Whetstone Pass

The first bounded audit should focus on these decisions rather than broad prose mutation:

1. Is the `snapshot` versus `follow_source` distinction complete and observable?
2. Does selected-occurrence rebinding use sufficient revision-independent identity without inheriting occurrence-key churn?
3. Can binding freshness and notification attempt-start freshness be evaluated deterministically from persisted facts?
4. Is asynchronous bounded reconciliation safe, or does any source mutation require additional transactionally persisted discovery pressure?
5. Are source terminal behavior and manual target override semantics complete?
6. Does the proposed model preserve granular Spine authority while actually eliminating operator choreography?
7. Are identity preimages, failure precedence, and readback obligations sufficiently closed to begin schemas and fixtures?
