# Spine Relative Temporal Bindings and Atomic Related-Task Creation

Status: Draft v0.2; not implemented and not advertised by the runtime
Scope: Explicit cross-item temporal derivation, bounded discovery/reconciliation, and atomic creation of a task that is part of an existing event
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
- `binding_revision_hash_derivation_version=spine.normalized-temporal-binding-revision-hash.v1`;
- `binding_catalog_version=spine.temporal-binding-catalog.v1`;
- `contract_version=spine.schedule-related-task-create.v1`;
- `response_contract=spine.schedule-related-task-create-response.v1`;
- `receipt_contract=spine.schedule-related-task-create-receipt.v1`;
- `reconcile_contract_version=spine.schedule-binding-reconcile.v1`;
- `reconcile_response_contract=spine.schedule-binding-reconcile-response.v1`;
- `reconcile_receipt_contract=spine.schedule-binding-reconcile-receipt.v1`;
- `list_contract_version=spine.schedule-binding-list.v1`;
- `list_response_contract=spine.schedule-binding-list-response.v1`;
- `list_cursor_version=spine.schedule-binding-list-cursor.v1`;
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
- bounded binding discovery and one-binding-at-a-time follow-source reconciliation;
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
- `relationship_id`, referencing the required stored `part_of` relation;
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
- `resolution_kind=initial|target_rescheduled|source_refreshed|detached|source_terminal|target_terminal|relationship_inactive`;
- `normalized_temporal_binding_revision_hash` and every version constant used by its preimage;
- `created_by_command_id`; and
- `created_at_utc`.

The current revision is the greatest persisted revision index for an active logical binding. Revisions are never updated in place.

### 5.4 Source scopes

`source_scope=item` is legal only when the source event has no active recurrence set. It resolves the event's current concrete start anchor.

`source_scope=selected_occurrence` is required when the source event is recurring. The request supplies both:

- the current `target_occurrence_key`, which proves exactly which current occurrence the caller selected; and
- the revision-independent `target_occurrence_selector`, which allows the same semantic source to be resolved after a recurrence revision.

Initial authoring requires the key and selector to resolve to exactly one current actionable occurrence. The composite itself atomically invokes the recurrence contract's Section 8 regeneration authority to produce or refresh active provenance for `consumer=temporal_binding`; callers MUST NOT pre-run the public `occurrence_provenance.regenerate` command. The existing recurrence consumer field is an open non-empty string, so `temporal_binding` requires registration in capability declarations and conformance fixtures but no new provenance identity model. Zero matches, multiple matches, stale recurrence facts, omitted occurrences, exclusions, or non-actionable provenance fail closed.

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
- the target item remains open and its current due anchor is semantically equal to the revision's target anchor;
- the logical binding remains active; and
- the required `part_of` relation remains active.

Otherwise the binding is computed as `stale`, `source_terminal`, `source_unresolved`, `target_diverged`, `target_terminal`, or `relationship_inactive`. These states are read-model facts derived from current canonical rows; a source mutation does not rewrite an old binding revision merely to label it stale.

Any notification opportunity or work row targeting the bound task due time is non-actionable while the binding is not `current`. Attempt-start freshness MUST check this invariant even when the work row was valid when materialized.

### 5.8 Reconciliation posture

Following is implemented by the bounded `schedule.binding.list` and `schedule.binding.reconcile` contracts in Section 7, not by a read-time illusion and not by unbounded fan-out inside a source mutation. Discovery is read-only. Each reconcile command targets exactly one active logical binding and either refreshes its source evidence, creates one ordinary next task version, resolves a terminal/conflict branch, repairs bounded notification work, or returns a receipt-bearing no-op.

The first runtime implementation MUST ship creation, discovery, reconciliation, readback, and attempt-start binding freshness together. Advertising create-time `follow_source` without the rest of that family is non-conforming.

### 5.9 Relational persistence

The implementation introduces three ordinary relational authorities:

- `relative_temporal_bindings`, one logical header per binding;
- `relative_temporal_binding_revisions`, immutable revision rows with a unique `(temporal_binding_id, revision_index)` and foreign keys to the exact source/target item versions, target anchor, relationship, recurrence revision, and occurrence provenance when present; and
- `temporal_binding_catalog_state`, exactly one singleton row containing the nonnegative integer `binding_catalog_generation` used only for cursor invalidation.

Semantic binding and selector facts MUST NOT be stored as opaque JSON identity blobs. Normalized selector children use the same relational representation and reconstruction rules as notification selected-occurrence selectors. The active-binding uniqueness constraint is `(target_item_id, target_anchor_role)` where `binding_status=active`. Revision indexes begin at `1`, are contiguous within one logical binding, and are assigned before the revision identity and hash are persisted.

The catalog generation begins at `0` when the migration creates the singleton. Every successful transaction that changes any fact capable of changing binding membership or Section 7.1 state increments it exactly once in that same transaction. Read-only operations, dry runs, compatible replays, receipt-only no-ops, and work-only reconciliation do not increment it. The generation is an invalidation watermark, not schedule truth, and no state predicate may consult its numeric value.

## 6. `schedule.related_task.create`

### 6.1 Request

The proposed request is a closed JSON object with exactly these required top-level fields:

- `contract_version=spine.schedule-related-task-create.v1`;
- `command_id`;
- `actor_subject_id`;
- `created_at_utc`;
- `source`;
- `task`;
- `relationship`;
- `temporal_binding`;
- `reminders`;
- `materialization`.

`delivery` is the only conditionally present top-level field: it is required exactly when `reminders` is non-empty and forbidden when `reminders=[]`. There are no omitted-field defaults for reminders or materialization. A zero-reminder request MUST carry `reminders=[]` and `materialization={"mode":"none"}`. These explicit values are request semantic facts and participate in replay comparison.

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

For `source.scope=selected_occurrence`, the handler derives the exact selector-local proof window from `specs/recurrence.md`: `range_basis=original_schedule`, `range_start` equal to the selector's canonical original scheduled fact, and `range_end` equal to that local-instant scheduled fact plus one wall-clock second. Through the recurrence regeneration service, it expands that complete window, intersects it with the single supplied current occurrence key, and derives the ordinary recurrence provenance slot, content hash, and provenance identity with `consumer=temporal_binding` and `producer=schedule.related_task.create`.

Equal active slot plus equal content retains the existing provenance row. Equal slot plus different current content atomically supersedes and replaces it. A missing predecessor creates one active row. No other occurrence slot is selected or superseded. Failure to form the proof window, select exactly the supplied key and selector, or produce current actionable provenance fails before any composite row commits.

### 6.3 Atomic persistence

One fresh non-dry-run success is one database transaction whose logical phases are:

1. validate the closed request and derive replay semantic facts;
2. resolve command-ID replay or collision;
3. verify schema, declared contracts, actor, and source version/lifecycle;
4. resolve the concrete source event start or selected occurrence and derive the selector-local proof window;
5. normalize the binding, derive the target instant, and validate task, relation, route, reminders, and materialization;
6. begin the atomic write and, for a selected occurrence, retain or produce current `consumer=temporal_binding` occurrence provenance;
7. create the task shell, common version `1`, task detail, and concrete due anchor;
8. create the active stored `part_of` relation from task to source event;
9. create the temporal-binding header and revision referencing the selected source provenance when applicable;
10. create the complete initial notification policy set;
11. expand and materialize the complete bounded selection when requested;
12. persist one composite audit and one composite command receipt;
13. run commit invariants and commit; and
14. read back receipt-bound evidence and fail closed on contradiction.

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

Notification, opportunity, provenance, and work identities retain their owning specifications. `normalized_temporal_binding_revision_hash` is the lowercase SHA-256 digest of Spine canonical JSON containing exactly `binding_revision_hash_derivation_version`, `binding_contract`, `binding_normalization_version`, `canonical_json_version`, `source_item_id`, `source_anchor_role`, `target_item_id`, `target_anchor_role`, `relationship_id`, `relationship_type=part_of`, `binding_mode`, conditionally present `source_terminal_behavior`, `source_scope`, conditionally present `source_anchor_id` for item scope, conditionally present normalized `target_occurrence_selector` for selected-occurrence scope, `source_target_version`, conditionally present `source_recurrence_revision_id`, canonical original `source_scheduled_fact`, `resolved_source_utc`, `offset_basis`, `offset_seconds`, `target_item_version`, target `local_date`, `local_time`, `timezone`, concrete `timezone_database_version`, `resolved_target_utc`, and `resolution_kind`. Other generated IDs, occurrence keys, provenance IDs, command IDs, actors, and creation/audit timestamps are excluded. Absent conditional facts are omitted rather than encoded as `null`.

The exact hash preimage and canonical ordering must be closed in the machine-contract phase before implementation begins.

### 6.5 Receipt and lifecycle

Fresh success stores `effect=related_task_schedule_created`. Compatible replay returns top-level `effect=related_task_schedule_create_replay` while the nested receipt retains the stored effect.

The response and receipt expose at least:

- task item ID, version, detail status, title, and subject roles;
- source event ID/version, source scope, source anchor or occurrence identities, temporal-binding occurrence-provenance identity and proof-window facts when selected, resolved source local/UTC time, timezone, and timezone-database version;
- relation ID, direction, type, and status;
- temporal binding ID/revision, mode, terminal behavior, offset, resolution state, and normalized revision hash;
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

## 7. Binding Discovery and Reconciliation

### 7.1 Closed binding state

Every binding read computes exactly one `binding_state` using this precedence:

1. `retired` when the logical binding is retired;
2. for `snapshot`, `snapshot_resolved` when the current target due anchor still equals the latest binding revision, otherwise `snapshot_diverged`;
3. for active `follow_source`, `target_terminal` when the target shell, task detail, or completion state is terminal;
4. `source_terminal` when the source shell or event detail is terminal;
5. `relationship_inactive` when the referenced stored `part_of` relation is absent or inactive;
6. `source_unresolved` when the named source anchor or selected-occurrence selector resolves zero or multiple current actionable occurrences;
7. `target_diverged` when the current target due anchor is not semantically equal to the latest binding revision and the target is not terminal;
8. `stale` when the source still resolves exactly once but current source item-version, recurrence-revision, occurrence-key, provenance, scheduled, timezone, or normalized-recurrence facts differ from the latest binding revision; and
9. `current` otherwise.

The enum is closed: `retired`, `snapshot_resolved`, `snapshot_diverged`, `current`, `stale`, `source_terminal`, `source_unresolved`, `target_diverged`, `target_terminal`, and `relationship_inactive`. Implementations MUST NOT collapse the specific non-current states into one undifferentiated stale value.

Target-anchor semantic equality compares exactly anchor kind, local date, local time, timezone, concrete timezone-database version, and resolved UTC instant after canonicalization; anchor-row identity alone is neither sufficient nor required. Source scheduled and timezone facts use the same byte-level canonical comparison plus source item and recurrence freshness facts named in Section 5.3.

### 7.2 `schedule.binding.list`

`schedule.binding.list` is the bounded read and discovery surface. Its closed request contains:

- `contract_version=spine.schedule-binding-list.v1`;
- optional `source_item_id`;
- optional `target_item_id`;
- optional `binding_mode=snapshot|follow_source`;
- optional `binding_status=active|retired`, defaulting to `active`;
- optional non-empty unique `binding_states` array using the Section 7.1 enum, defaulting to all states legal for the selected status and mode;
- optional decimal-string `limit` in `1..1000`, defaulting to `100`;
- optional opaque `cursor`; and
- optional `bounded` boolean.

At least one endpoint filter is required unless `bounded=true`. `binding_states` is normalized into the fixed Section 7.1 precedence before request comparison; duplicate values fail with `invalid_request`, `field=binding_states`. A cursor is mutually exclusive with changing any repeated filter or limit fact. The command performs no write, audit, receipt, provenance generation, reconciliation, or adapter action.

Cursor invalidation uses a persisted decimal-string `binding_catalog_generation`, not an unbounded hash over every matching binding. This monotonic invalidation watermark increments transactionally whenever a commit can change binding membership or computed state: binding header/revision/status, source or target current item version/lifecycle, source recurrence revision, or referenced relation status. It is not schedule truth and never decides a binding state; it only proves that a paginated read still observes the same catalog generation. Conservative increments caused by unrelated item mutations are legal and only invalidate cursors.

Results order by the fixed Section 7.1 state precedence, then `source_item_id`, `target_item_id`, and `temporal_binding_id`. Each row returns the binding header, relationship identity/status, latest revision and hash, source and target version/anchor/recurrence/provenance summaries, offset, computed state, `reconcile_required`, `automatic_reconcile_eligible`, `operator_decision_required`, and the exact version/revision values required by `schedule.binding.reconcile`.

`reconcile_required=true` exactly for an active `follow_source` binding whose state is not `current`. `automatic_reconcile_eligible=true` exactly for `stale`, `target_terminal`, `relationship_inactive`, or `source_terminal` whose stored behavior is `cancel_target` or `detach_at_last_value`. `operator_decision_required=true` exactly for `source_unresolved`, `target_diverged`, or `source_terminal` whose stored behavior is `require_decision`. The two disposition booleans are never both true. Snapshot, retired, and current rows set all three booleans false.

The first page reads one `binding_catalog_generation` inside the same database read snapshot as the selected rows. The cursor payload contains `cursor_version=spine.schedule-binding-list-cursor.v1`, every accepted normalized query fact, that generation, and the last returned ordering tuple. The opaque cursor is unpadded base64url of Spine canonical cursor JSON, followed by `.`, followed by the lowercase SHA-256 digest of those exact bytes. A malformed cursor or changed query fact fails with `invalid_request`, `field=cursor`; a changed catalog generation fails with `stale_cursor`, `field=cursor`. Every page returns the accepted generation. Terminal output uses `has_more=false` and `next_cursor=null`.

Tickerd or an operator may repeatedly list non-current active follow bindings. Tickerd invokes one reconcile command only for rows with `automatic_reconcile_eligible=true`; it surfaces but does not repeatedly receipt-churn rows requiring an operator decision. Discovery cadence is deployment configuration, not canonical ledger truth. A deployment that claims automatic follow-source operation MUST configure this bounded loop and expose its health operationally. Safety does not depend on sweep timing because Section 5.7 attempt-start freshness independently blocks stale work.

### 7.3 `schedule.binding.reconcile` request

The reconcile request is a closed object with these required fields:

- `contract_version=spine.schedule-binding-reconcile.v1`;
- `command_id`;
- `actor_subject_id`;
- `reconciled_at_utc`;
- `temporal_binding_id`;
- exact `target_temporal_binding_revision_id`;
- exact `source_target_version`;
- exact `target_target_version`;
- `expected_binding_state`; and
- explicit `materialization`, using the exact `schedule.create` `none|bounded` union.

`source_recurrence_revision_id` is required exactly when the latest binding revision uses `source_scope=selected_occurrence` and the source still owns a recurrence set. It is forbidden for `source_scope=item`.

Optional `operator_resolution` has the closed values `cancel_target` and `detach_at_current_target`. `cancel_target` is accepted only for `source_terminal` with stored behavior `require_decision` or for `source_unresolved`. `detach_at_current_target` is accepted for `current`, `stale`, `source_terminal` with stored behavior `require_decision`, `source_unresolved`, or `target_diverged`. It is forbidden in every other state. `cancel_target` performs the ordinary terminal task transition. `detach_at_current_target` retires the binding and preserves the target's current concrete due anchor. This supplies a safe explicit path for proactively abandoning follow behavior or resolving divergence without silently rewriting history.

Bounded materialization is legal only when the resolution leaves an open target task with a current concrete binding and at least one current active notification policy. Its `item_relative` offsets use the resulting target due UTC instant; its local range uses the resulting target timezone and pinned database version. Evaluation timestamp, complete-range selection, limit, no-prefix behavior, and route validation are exactly those of `schedule.create`. Terminal, detached, relationship-inactive, target-terminal, or unresolved decision branches require `materialization={"mode":"none"}`. Mandatory stale-work reconciliation still runs in every branch.

### 7.4 Resolution branches

After exact freshness checks, the command resolves one branch:

- any state that legally accepts `operator_resolution=detach_at_current_target`: create one detached binding revision, retain the current task version and anchor, and retire the binding;
- `current`: no binding or item truth changes; bounded materialization may repair missing current work.
- `stale` with changed derived target schedule: create one next task version with a new concrete due anchor and one next binding revision with `resolution_kind=target_rescheduled`.
- `stale` with byte-equal derived target schedule but changed source freshness: retain the current task version and anchor and create one next binding revision with `resolution_kind=source_refreshed`.
- `source_terminal` with stored `cancel_target`, or with `require_decision` plus `operator_resolution=cancel_target`: create one next cancelled task version, one terminal binding revision, and retire the binding.
- `source_terminal` with stored `detach_at_last_value`: create one detached binding revision, retain the current task version and anchor, and retire the binding.
- `source_terminal` with stored `require_decision` and no operator resolution: retain binding and task truth and return `resolution_outcome=decision_required`.
- `source_unresolved` with `operator_resolution=cancel_target`: cancel exactly as requested. Without an operator resolution, retain binding and task truth and return `decision_required`.
- `target_diverged` without detach resolution: fail with `semantic_conflict`, `field=operator_resolution`; the command MUST NOT overwrite the divergent target.
- `target_terminal`: create one `target_terminal` binding revision against the existing terminal target version and retire the binding.
- `relationship_inactive`: create one `relationship_inactive` binding revision at the current target anchor and retire the binding.

Snapshot and already-retired bindings are not reconcile targets and fail without mutation. A source mutable fact that changes after request construction changes the actual binding state or exact source version/revision and therefore fails freshness rather than executing a different branch.

### 7.5 Selected-occurrence provenance during reconciliation

For a selected-occurrence binding in `current` or `stale`, reconciliation derives the same one-second `original_schedule` proof window as Section 6.2 and resolves the stored revision-independent selector against current recurrence truth. Through the recurrence regeneration service, exactly one actionable result atomically retains or replaces `consumer=temporal_binding` provenance using `producer=schedule.binding.reconcile` before a successor binding revision or work is written.

The new binding revision records the current occurrence key and active provenance identity, while its normalized semantic hash uses the revision-independent selector rather than the revision-bound key. A zero/multiple/non-actionable result becomes `source_unresolved`; it does not widen the range, guess a successor, or persist new provenance. Old provenance remains historical but cannot authorize action.

### 7.6 Notification-work reconciliation

Every reconcile invocation classifies the complete affected set of target notification work after the resolution branch is known. The unstarted and protected predicates are exactly those in `specs/schedule-operations.md`.

An eligible zero-attempt row with no side-effect attempt is cancelled when its target schedule, item/policy version, occurrence provenance, routing, parent lifecycle, or temporal-binding freshness is no longer current. `specs/notifications.md` owns the conditional `notification_temporal_binding_stale` cancellation reason and extended precedence imported by this family: it is ordered after `notification_occurrence_stale` and before `notification_routing_changed`. The ontology imports the same attempt-start predicate. Persistence constraints, machine contracts, and behavioral tests for the added value MUST ship atomically with `spine.relative-temporal-binding.v1`; runtimes that do not advertise that family MUST NOT return it. When both target time and binding freshness changed, existing `notification_target_changed` takes precedence.

In-progress, retry, and terminal work remains protected historical evidence. Returned `cancelled_work_instance_ids`, `retained_work_instance_ids`, `protected_stale_work_instance_ids`, and `created_work_instance_ids` are pairwise disjoint and classify every selected row exactly once. No branch invokes an adapter or creates a side-effect attempt.

When reconciliation creates a next task version, unchanged active notification intents and policies copy forward under their ordinary lineage rules before bounded replacement work is expanded. `materialization.mode=none` performs all mandatory cancellation but creates no replacement work. `mode=bounded` uses the complete range, provenance, limit, no-prefix, and route rules from `schedule.create` against successor truth.

### 7.7 Effects, audit, and transaction

`resolution_outcome` is closed over `target_rescheduled`, `source_refreshed`, `source_unchanged`, `target_cancelled`, `binding_detached`, `target_terminal_retired`, `relationship_inactive_retired`, and `decision_required`. The stored command-receipt effect is selected from this table:

| Resolution outcome | `work_changed=false` | `work_changed=true` |
|---|---|---|
| `target_rescheduled` | `binding_target_rescheduled` | `binding_target_rescheduled_and_work_reconciled` |
| `source_refreshed` | `binding_source_refreshed` | `binding_source_refreshed_and_work_reconciled` |
| `source_unchanged` | `binding_reconcile_noop` | `binding_work_reconciled` |
| `target_cancelled` | `binding_target_cancelled` | `binding_target_cancelled_and_work_reconciled` |
| `binding_detached` | `binding_detached` | `binding_detached_and_work_reconciled` |
| `target_terminal_retired` | `binding_target_terminal_retired` | `binding_target_terminal_retired_and_work_reconciled` |
| `relationship_inactive_retired` | `binding_relationship_inactive_retired` | `binding_relationship_inactive_retired_and_work_reconciled` |
| `decision_required` | `binding_decision_required` | `binding_decision_required_and_work_reconciled` |

One fresh success is one transaction. It validates and derives the complete branch and work classification before mutation, then writes selected provenance, task version/anchor, copied policy truth, binding revision/status, work reconciliation/materialization, one composite audit when truth or work changed, and one command receipt. A no-op or decision-required result with unchanged work writes only the receipt. Any pre-commit failure rolls back every selected row.

Reconcile command-derived identities use `command=schedule.binding.reconcile` and the shared command-id derivation with `/target/scheduled_time` for a replacement due anchor, `/temporal_binding/revision` for a successor binding revision, `/audit` for the composite audit, and `/` for the receipt. Copied policies and newly materialized work retain their owning content-addressed and copy-forward specifications. `truth_changed=true` for every resolution outcome except `source_unchanged` and `decision_required`; `work_changed` reflects any cancellation or creation. A truth-changing transaction increments `binding_catalog_generation` exactly once; work-only and receipt-only outcomes do not.

### 7.8 Response, dry run, and replay

The response returns `response_contract=spine.schedule-binding-reconcile-response.v1`, top-level and stored effects, resolution outcome, truth/work booleans, prior/current binding revisions, binding state before and after, source/target/relationship facts, selected-occurrence provenance when applicable, prior/result task versions and anchors, policy lineage, complete work-classification arrays, materialization summary, audit ID when written, and `receipt_contract=spine.schedule-binding-reconcile-receipt.v1`.

Dry run evaluates the same branch and would-be identities against one read snapshot and writes nothing. Compatible replay is resolved before current binding, source, target, recurrence, relationship, timezone, or materialization checks; it returns top-level `effect=schedule_binding_reconcile_replay` plus the original stored receipt and performs no new reconciliation.

## 8. Integration with Existing Reads and Mutations

Implementation of this family requires additive readback:

- `schedule.show` accepts `relations` and `temporal_bindings` include values and returns the current concrete schedule plus binding mode, latest revision, computed state, source/target evidence, offset, relationship identity, and reconcile inputs;
- `agenda.show` returns a compact binding summary and distinguishes an open task from the actionability of its derived schedule;
- `relation.list` continues to return the ordinary stored `part_of` row and derived `contains` alias without temporal inference; and
- `schedule.binding.list` is the canonical bounded discovery surface; agents and workers MUST NOT use raw SQL for binding discovery.

A stale binding does not erase the task from canonical reads. It makes the derived due schedule and schedule-dependent notification work non-actionable until reconciliation or explicit resolution.

Direct `schedule.update` replacement of a due anchor governed by an active `follow_source` binding fails with `semantic_conflict`, `field=temporal_binding_id`. The operator may first use `schedule.binding.reconcile` with `operator_resolution=detach_at_current_target` when the binding is divergent or otherwise requires a decision, then update the now-unbound task. Snapshot-bound tasks may be rescheduled normally; readback changes from `snapshot_resolved` to `snapshot_diverged` without changing historical binding evidence.

Ordinary target completion or cancellation remains authoritative. It does not synchronously fan out into the binding table; the binding becomes `target_terminal`, all future schedule-dependent work fails freshness immediately, and the next bounded reconciliation retires the binding. Relation inactivation behaves analogously through `relationship_inactive`.

Source schedule or recurrence mutations do not synchronously enumerate or mutate dependent tasks and do not need a fan-out marker for safety. They make affected bindings deterministically non-current by version/revision comparison. Tickerd's configured bounded discovery loop supplies eventual reconciliation; the attempt-start freshness gate supplies immediate delivery safety. Source mutation receipts therefore do not claim dependent reconciliation.

## 9. Validation and Failure Posture

### 9.1 Write validation order

Both create and reconcile use this ordered posture:

1. parse a closed JSON object and validate field shapes;
2. validate command identifier, contract version, command identity, actor, and action timestamp;
3. resolve global command-ID collision or compatible same-command replay;
4. verify ledger schema and the complete advertised contract family;
5. resolve the binding/source/target identities required by the command;
6. validate shell, item type, detail lifecycle shape, binding mode/status, and referenced relationship facts;
7. validate exact item, binding-revision, and recurrence-revision freshness;
8. validate conditional request-field shapes and enum membership without yet choosing a state-dependent branch;
9. resolve pinned timezone data and delivery targets;
10. resolve the source anchor or selected occurrence, compute actual binding state, and derive temporal-binding provenance when the selected branch requires source resolution;
11. compare `expected_binding_state` when present and validate state-dependent operator resolution;
12. normalize derived target, reminder/policy, materialization, work classification, identities, audit, and receipt;
13. begin one write transaction, persist every selected effect, run invariants, and commit; and
14. read back receipt-bound evidence and fail closed on contradiction.

Compatible replay precedes current lifecycle, freshness, timezone, route, occurrence, and materialization checks. Within Phase 7, binding revision, source item version, source recurrence revision, then target item version are checked in that order. Expected binding state is compared only in Phase 11, after the state has been deterministically computed.

### 9.2 Failure matrix

| Command | Condition | Code | Field |
|---|---|---|---|
| create | source item is not an event | `wrong_item_type` | `source.item_id` |
| create | source event or shell is terminal | `invalid_state_transition` | `source.item_id` |
| create | source target version is stale | `stale_version` | `source.target_version` |
| create | scope disagrees with recurrence state | `invalid_request` | `source.scope` |
| create | selected occurrence key/revision is stale | `stale_version` | narrowest source occurrence field |
| create | selector proof window cannot be formed | `semantic_conflict` | `source.target_occurrence_selector` |
| create | selected occurrence resolves zero or multiple times | `semantic_conflict` | `source.target_occurrence_selector` |
| create | source occurrence is not actionable | `semantic_conflict` | `source.target_occurrence_key` |
| create, list, or reconcile | pinned timezone data required to resolve a source is unavailable | `environment_failure` | `source_schedule.timezone_database_version` |
| create | offset is outside the Version 1 bound | `invalid_request` | `temporal_binding.offset_seconds` |
| create | snapshot supplies terminal behavior | `invalid_request` | `temporal_binding.source_terminal_behavior` |
| create | reminders field is omitted | `missing_required_field` | `reminders` |
| create | materialization field is omitted | `missing_required_field` | `materialization` |
| create | reminders exist without delivery | `missing_required_field` | `delivery` |
| create | delivery exists with `reminders=[]` | `invalid_request` | `delivery` |
| create | bounded materialization has no reminders | `invalid_request` | `materialization.mode` |
| create | relation or binding uniqueness conflicts | `semantic_conflict` | `relationship` or `temporal_binding` |
| list | no endpoint and `bounded` is not true | `missing_required_field` | `source_item_id` |
| list | cursor query facts differ | `invalid_request` | `cursor` |
| list | cursor snapshot changed | `stale_cursor` | `cursor` |
| reconcile | binding is snapshot or already retired | `invalid_state_transition` | `temporal_binding_id` |
| reconcile | binding revision differs | `stale_version` | `target_temporal_binding_revision_id` |
| reconcile | source item version differs | `stale_version` | `source_target_version` |
| reconcile | source recurrence revision differs | `stale_version` | `source_recurrence_revision_id` |
| reconcile | target item version differs | `stale_version` | `target_target_version` |
| reconcile | actual state differs from expected state | `stale_version` | `expected_binding_state` |
| reconcile | operator resolution is illegal for actual state | `invalid_request` | `operator_resolution` |
| reconcile | target diverged without detach resolution | `semantic_conflict` | `operator_resolution` |
| reconcile | bounded materialization is requested for a non-current result | `invalid_request` | `materialization.mode` |
| either write | required provenance cannot be retained or written atomically | `runtime_failure` | `occurrence_provenance` |
| either write | commit/readback evidence disagrees | `runtime_failure` | omitted unless singular |

Request-shape errors and CLI exits inherit `specs/agent-command-contract.md`. A `source_unresolved` or `source_terminal` branch requiring a decision is a successful, receipt-bearing semantic result rather than a failure when its exact expected state and request fields are valid.

## 10. Initial Contract and Fixture Plan

Before runtime work, add:

- shared relative-temporal-binding and binding-state schemas;
- create request, response, receipt, and failure schemas;
- list request, response, and cursor schemas;
- reconcile request, response, receipt, and failure schemas;
- the `temporal_binding` provenance consumer to supported-consumer declarations and conformance fixtures, and the conditionally owned `notification_temporal_binding_stale` value to relational constraints and machine contracts;
- a fixture manifest and structural validator tests;
- computed identity vectors for task, relation, binding, revision, anchor, provenance, cursor, audit, receipt, and normalized binding-revision hash; and
- behavioral transaction, replay, stale-source, recurrence, route, materialization, discovery, readback, reconciliation, and attempt-start freshness tests.

Minimum positive fixtures:

1. snapshot task at event start with `reminders=[]` and explicit materialization none;
2. snapshot task before event with one reminder and bounded work;
3. follow-source task at a non-recurring event;
4. task bound to one selected recurring occurrence with composite-produced provenance;
5. binding list pagination and stale cursor;
6. source reschedule producing a new task version and work reconciliation;
7. source-only version change producing a new binding revision without a task version;
8. source terminal behavior for each stored value;
9. source-unresolved and target-diverged operator resolution;
10. target-terminal and relationship-inactive retirement;
11. compatible create and reconcile replay after later source movement; and
12. dry runs with deterministic would-be identities and no rows.

Minimum failure fixtures:

1. wrong source type and stale source version;
2. recurring source with `scope=item`;
3. stale, excluded, missing, or multiply resolved selected occurrence;
4. invalid offset;
5. omitted reminders, omitted materialization, invalid delivery/reminder pairing, and bounded materialization without reminders;
6. missing or mismatched delivery target;
7. injected failures after provenance, task, relation, binding, policy, work, and receipt phases proving total rollback;
8. reconcile against snapshot, retired, stale binding revision, stale source/target/revision, or changed expected state;
9. illegal operator resolution and bounded materialization on a non-current result;
10. direct target schedule update rejected while follow binding governs it; and
11. stale follow binding rejected at delivery attempt start even before the discovery worker runs.

## 11. Acceptance Criteria

This contract family is ready to implement only when:

1. two independent implementations derive byte-identical normalized binding-revision hashes, command IDs, provenance IDs, cursors, and receipts from the fixture corpus;
2. `part_of` without a binding demonstrably produces no temporal effect;
3. the composite either commits the complete provenance/task/relation/binding/reminder/work bundle or no selected row;
4. all granular child identities remain independently queryable;
5. snapshot and follow-source behavior differ exactly as specified after source movement;
6. selected recurring-occurrence creation and reconciliation produce their own bounded current provenance without caller choreography;
7. a changed derived target creates one ordinary next task version, while a source-only refresh creates only a binding revision;
8. discovery is bounded, ordered, cursor-bound, and usable without raw SQL;
9. every closed reconciliation outcome and work-changed branch has a fixture and deterministic receipt effect;
10. stale, unresolved, terminal, divergent, or relation-inactive follow bindings cannot authorize reminder delivery even before reconciliation;
11. compatible replay returns original receipt facts without reevaluating current source, relationship, route, or materialization state;
12. readback distinguishes task lifecycle, binding state, reminder work, and delivery lifecycle;
13. no command performs delivery or creates a `side_effect_attempts` row; and
14. the operator guide can express success or decision pressure without hiding the relation, binding mode, provenance, or stale state.

## 12. Questions for the Focused Recheck

The next bounded audit should verify:

1. whether the closed list/reconcile family makes accepted `follow_source` creation buildable without invention;
2. whether selector-local provenance generation composes exactly with the recurrence authority;
3. whether state precedence, expected-state freshness, resolution branches, and effects are mutually exhaustive;
4. whether periodic bounded discovery plus attempt-start freshness is sufficient without source-mutation fan-out markers;
5. whether source-terminal, source-unresolved, target-diverged, target-terminal, and relationship-inactive paths leave safe operator outcomes;
6. whether work cancellation reason precedence is compatible with the notification authority; and
7. whether any remaining gap blocks schemas and structural fixtures.
