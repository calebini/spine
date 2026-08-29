# Spine Implementation Plan

Status: Deterministic notification rendering implemented and verified
Last reconciled with repository state: 2026-08-24

This is a non-normative delivery plan. The specifications and machine-readable contracts remain authoritative.

## Planned Sustaining Slice: Canonical Owner-Scope Discovery

`specs/owner-scope-discovery.md` defines a bounded read-only `owner_scope.list`
projection so agents can discover active system, subject, and subject-group owner
scopes before creating archetypes, notification profiles, and bindings. The slice
removes routine table knowledge from owner selection while retaining existing
per-owner catalog list commands. It requires closed schemas, fixtures, cursor and
generation tests, indexed bounded selection, runtime registry parity, and a no-write
proof before advertisement.

## Delivered Slice: Deterministic Notification Rendering

The schema-9 runtime now turns admitted ordinary reminder work into deterministic,
concise `en-CA` prose at attempt start. Rendering uses the proposed attempt time plus
current canonical title, target, item type, pinned target timezone, occurrence or
follow-source binding evidence, and primary location. Relative phrases cover the
six-hour window; longer horizons use calendar wording such as `at 2 PM tomorrow`.

Each rendering is immutable evidence linked one-to-one with its side-effect attempt.
The rendering and `attempt_status=started` row commit atomically, the OpenClaw request
envelope binds rendering identity/content hash/exact body, compatible replay cannot
authorize another transport call, retries receive new attempt-time evidence, and
`schedule.show` nests stored evidence under the corresponding attempt. The public
schema, schema-object manifest, computed vector, failure oracles, migration, runtime
capability declarations, and operator documentation ship with the implementation.

## Delivered Sustaining Slice: Scheduler Planning and Durable No-Op Suppression

The Tickerd-driven horizon cycle now performs bounded read-only Spine planning before
dispatching receipt-bearing provenance or notification-work operations. Active policy
presence alone no longer causes materialization. A plan dispatches only when it can
create missing actionable work, repair recurrence provenance needed by the evaluated
horizon, or reconcile stale cancellable work with `status=eligible`, zero attempts,
and no side-effect-attempt evidence.

Past exhausted one-shot and bounded policies, already-materialized opportunities, and
recurrence horizons with no qualifying occurrence now produce zero ledger growth.
`deliver_within` remains eligible through its exact grace interval; disabled-policy
work remains discoverable for reconciliation; existing retry, in-progress, and
terminal work remains protected history. The dispatch limit counts actionable plans
rather than raw active-policy rows, preventing exhausted items from starving later
work. Explicit `notification_work.materialize` retains its receipt-bearing
zero-selected, all-retained, changed, collision, and replay semantics.

Behavioral proof covers exhausted and future one-shots, exact late grace, local-time
target-relative expansion, equivalent-work suppression, explicit no-op receipts,
policy-edit and policy-disable reconciliation, exhausted and active recurrence,
repeat-cycle provenance suppression, and dispatch-limit fairness. The complete suite
passes without a schema migration or public command change.

## Delivered Fat Slice: Atomic Schedule Creation

The audited `spine.schedule-create.v2` contract is implemented as one environment-sized delivery. The operator-facing `schedule.create` command creates an event or task, its local-instant anchor, optional archetype and notification-profile application, optional inherited recurrence, complete initial reminder-policy set, optional occurrence provenance, and optional bounded notification work in one transaction and returns one replay-safe composite receipt.

The delivery includes:

- transport-neutral command registration plus the `spine-command ... schedule create` CLI alias;
- normalized `CommandContext.delivery_target_defaults` resolution without route creation or approval;
- exact timezone-version pinning, fail-closed initial local-time resolution, and internal UTC horizon normalization;
- direct reuse of canonical recurrence, notification, provenance, opportunity, and work engines without public subcommand chaining;
- one version-`1` item, one composite audit, and one composite command receipt with full rollback on any child failure;
- compatible replay from stored result evidence, deterministic dry run, and post-commit receipt/evidence verification;
- behavioral coverage for event/task, recurrence, policy-only/materialized branches, routes, DST, replay, semantic uniqueness, injected rollback, and the no-send boundary; and
- runtime command/version declarations plus agent/operator documentation aligned with the executable surface.

Behavioral proof covers non-recurring events, recurring tasks, policy-only and bounded branches, named and explicit routes, recurrence provenance, response-schema conformance, replay without current-environment re-resolution, dry-run identity equivalence, DST ambiguity rejection, task-role semantic uniqueness, injected failure after each write phase, and the no-send boundary.

This original slice required no schema migration because schema 7 already owned every canonical row required by schedule creation. Schema 8 was later added for explicit relative temporal bindings.

## Delivered P0: Canonical Schedule Verification

The `spine.schedule-show.v1` read model is implemented as the operator verification boundary over the current schema. It returns current item and schedule facts, concrete timezone-version and UTC-resolution evidence, recurrence, current notification policies and intent IDs, bounded work and attempt detail, route snapshots, relations and temporal bindings when requested, complete status counts, and separate authored/opportunity/work/delivery lifecycle dimensions. The direct CLI `--item-id` and `--include` form maps to the same transport-neutral command request.

The related documentation audit treats `notification_policies.policy_id` and the public `notification_policy_id` alias as distinct intentional surfaces, replaces item-specific operator SQL with `schedule.show`, and documents `timezone_database_version.kind=system_current` as a one-time pin to a concrete version. Omission remains invalid and compatible replay retains the original resolved version.

## Delivered Operator Layer: Compact Receipts and Countdown Builder

The `spine.schedule-compact.v1` CLI projection provides audit-complete, chat-sized success output for `schedule.create` and `schedule.show` while retaining full JSON as the default. It carries item/command/receipt identity, scheduled time and pinned timezone data, policy and intent IDs, bounded work identity, route source/target references, and separate authoring, expansion, materialization, attempt, and outcome states.

The read-only `schedule.build` command implements `spine.schedule-countdown-builder.v1`. It compiles an explicit reference instant plus relative event delay and reminder cadence into a normal, fully pinned `schedule.create` request. Its first tested profile—event in two hours, remind every 30 minutes until start—resolves the route and timezone version, bounds four work opportunities, performs no write, and feeds the existing atomic authoring path unchanged.

## Delivered Fat Slice: Operational Schedule Lifecycle

`specs/schedule-operations.md` defines the implemented contract family for daily schedule operation after creation:

- `agenda.show` provides one bounded cross-item local-time agenda with recurrence expansion and snapshot-bound pagination;
- `schedule.update` atomically changes whole-item schedule truth, whole-series recurrence, reminder policies, and delivery routing while reconciling obsolete never-started work and optionally materializing a replacement horizon; and
- `schedule.cancel` performs a type-neutral terminal transition and cancels all never-started notification work without rewriting started or terminal evidence.

The implementation is one environment-sized service-layer slice over the canonical scheduling engines rather than public subcommand chaining. It declares the complete version family, exposes all three commands through transport-neutral dispatch and the generic CLI, writes deterministic receipts and audits, preserves immutable canonical detail, supports dry run and replay, and has behavioral coverage for agenda selection/cursors, recurrence replacement, reminder replacement, reconciliation, bounded materialization, cancellation, and no-send behavior. This slice itself required no migration.

## Delivered Fat Slice: Relative Temporal Bindings and Atomic Related Tasks

`specs/relative-temporal-bindings.md` is implemented as one schema-8 family. `schedule.related_task.create` atomically creates a normal task, concrete due anchor, stored `part_of` relation, explicit `snapshot|follow_source` binding and immutable first revision, optional reminders, optional bounded work, one audit, and one receipt. A selected recurring source also creates or refreshes bounded `consumer=temporal_binding` occurrence provenance in that transaction.

`schedule.binding.list` provides bounded state-ordered discovery with generation-bound cursors. `schedule.binding.reconcile` resolves one follow-source binding at a time, creating an ordinary next task version when derived due time changes, refreshing only binding evidence for source-only changes, applying terminal/detach/decision outcomes, and reconciling notification work without sending. Tickerd's horizon cycle invokes only automatically eligible branches.

Safety is independent of sweep cadence: direct due replacement is rejected while a follow binding governs the task, agenda/readback expose stale or decision state without erasing the task, and work processing checks binding freshness before a side-effect attempt can start. Structural schemas and initial fixtures live in `contracts/relative-temporal-binding-fixture-manifest.json`; runtime coverage includes atomic rollback, replay, dry run, selected occurrences, source movement, source-only refresh, snapshot divergence, cursor invalidation, scheduler terminal handling, agenda actionability, and stale-delivery rejection.

## Delivered Additive Slice: Primary Schedule Location

`specs/schedule-primary-location.md` activates the existing canonical `locations` and
version-scoped `item_locations` model across the high-level scheduling surfaces without
adding another location authority or a schema migration. `schedule.create` and
`schedule.update` accept closed inline-create/reference forms; `schedule.show` and
`agenda.show` expose an explicitly requested clean view; `schedule.build` passes the
public authoring value through; and compact create/show receipts preserve the complete
bound view when present.

The implementation derives deterministic location and item-location identities,
copies retained primary roles across item versions, preserves immutable historical
rows on replace/clear, validates references inside the transaction, and snapshots
replay evidence. Location timezone remains descriptive and cannot alter schedule time,
location-only mutation does not stale recurrence provenance or reminder work, and
authoring still performs no send. Structural fixtures plus behavioral tests cover
inline/reference creation, dry run, replay after metadata refresh, read projections,
no-op/copy-forward behavior, replace/clear, missing references, rollback, work
retention, and runtime capability declarations.

## Delivery Goal

Ship one environment-sized implementation that supports the complete path from a structured recurrence or notification command to deterministic virtual results, canonical relational state, durable notification work, Tickerd processing, and a recorded adapter attempt.

The delivery is intentionally broad because recurrence identity, occurrence provenance, notification scheduling, reconciliation, and work authorization are one connected system. Internal gates isolate faults; they are not separate deployment units.

## Authority Map

- `specs/recurrence.md`: recurrence normalization, identity, expansion, mutation, lineage, and occurrence provenance.
- `specs/notifications.md`: notification schedules, opportunities, late handling, materialization, and reconciliation.
- `specs/notification-rendering.md`: deterministic attempt-time prose, immutable evidence, and adapter-envelope binding.
- `specs/operational-resilience.md`: draft cross-cutting resource bounds, failure containment, recovery, dependency admission, and sustained-operation proof.
- `specs/ontology.md`: relational authority and lifecycle invariants.
- `specs/agent-command-contract.md`: public command and receipt behavior.
- `specs/schedule-show.md`: canonical aggregate schedule and delivery-lifecycle readback.
- `specs/schedule-operator-tools.md`: relative countdown compilation and compact operator projection.
- `specs/schedule-operations.md`: implemented cross-item agenda and atomic schedule update/cancel reconciliation lifecycle.
- `specs/schedule-primary-location.md`: implemented primary-location authoring, mutation, builder, readback, and compact-projection extension.
- `specs/relative-temporal-bindings.md`: implemented atomic related-task creation, binding persistence/state, bounded discovery, reconciliation, and attempt freshness.
- `contracts/schemas/recurrence-*.schema.json` and `contracts/schemas/notification-*.schema.json`: public machine shapes.
- `contracts/vector-manifest.json`: computed identity and behavior evidence.

## Delivered Surface

### Deterministic scheduling engine

- Canonical `local_date`, `local_instant`, and `instant_utc` schedule facts.
- `DAILY`, `WEEKLY`, `MONTHLY`, and `YEARLY` frequencies.
- Positive intervals, count and inclusive-until bounds, selector defaults, weekday/month/month-day/set-position selectors, and week starts.
- Invalid-calendar-date omission, pinned timezone facts, nonexistent-local omission, and earliest-instant ambiguous-time resolution.
- Rdates, exdates, detail/lifecycle overrides, moved occurrences, duplicate collapse, deterministic ordering, diagnostics, density limits, bounded ranges, and revision-bound cursors.
- Exact original-schedule and expressed-time range behavior, including occurrences moved into the requested expressed range.

### Canonical persistence and migration

- Schema version 8, retaining schema-7 recurrence and notification authority while adding explicit temporal-binding headers, immutable revisions, and a cursor-invalidation catalog generation.
- Occurrence provenance snapshots, slot uniqueness, supersession, and unresolved-range reports.
- Stable notification-intent identities, immutable policy versions, structured schedule rows, boundaries, selectors, and occurrence target selectors.
- Opportunity-bound work snapshots and fail-closed work/attempt constraints.
- One transactional migration bundle with clean-prior-schema, structural, constraint, rollback, and scheduling-data preflight coverage.
- One active scheduling authority after migration.

### Commands and mutations

- Structured recurrence authoring on event-start and task-due anchors.
- `item.occurrences` with bounded pagination and diagnostics.
- `recurrence.instance.add`, `.remove`, and `.override`.
- `recurrence.series.edit` with `one`, `this_and_following`, and `whole_series` scopes.
- `occurrence_provenance.regenerate` with closed effects and report behavior.
- `reminder.create`, `.edit`, and `.disable` for structured notification policies.
- `notification.opportunities` and `notification_work.materialize`.
- `schedule.show` with bounded policy, work, route, receipt, and attempt evidence.
- `schedule.related_task.create`, `schedule.binding.list`, and `schedule.binding.reconcile`, plus relation/binding schedule readback and agenda actionability.
- Deterministic replay, stale-version checks, dry runs, receipts, and atomic item/supporting-set writes.

### Notification and delivery path

- Once, explicit-offset, fixed-elapsed repeat-window, and local-calendar notification schedules.
- Item, each-occurrence, and selected-occurrence application scopes.
- Stable intent, schedule, slot, opportunity, cursor, and work identity.
- Explicit late handling and deterministic opportunity diagnostics.
- Duplicate-safe materialization and unstarted-work reconciliation after policy, target, routing, recurrence, occurrence, or lifecycle changes.
- Tickerd horizon reconciliation, observe-only execution, active bounded execution, and fake OpenClaw evidence.
- `side_effect_attempts` as the sole adapter-attempt ledger.

### Contract evidence

- Full Draft 2020-12 validation for all schemas, manifests, and contract fixtures.
- Computed recurrence and notification vectors generated through the executable normalizers and expanders.
- Published canonical inputs, normalized output, preimage JSON, digests, and expansion results for the two primary scenarios:
  - every three days at 08:00 local;
  - every hour during the six hours before an event.

## Final Acceptance Evidence

The fat slice passed the following consolidation and proof campaign:

1. Keep normative specs, README, operator guide, and this plan aligned with the executable surface.
2. Remove dead prototype helpers and obsolete golden artifacts so only the canonical command family is discoverable.
3. Run strict type checks and focused style checks over every changed scheduling module.
4. Run the complete test suite with the sibling Tickerd source available so integration tests execute rather than skip.
5. Run the official schema/fixture validator and computed-vector corpus independently.
6. Rehearse migration from a clean schema-version-6 ledger, migration preflight rejection, injected rollback, and post-migration verification.
7. Run a bounded canary sequence: seed, observe-only, active with fake OpenClaw, inspect work and `side_effect_attempts`.
8. Review the diff for one-authority behavior, accidental direct-send paths, secret material, and unrelated user changes.

## Acceptance Campaign

The environment handoff should support one concentrated user test campaign:

1. Author every three days at 08:00 in an IANA timezone, cross a DST boundary, and verify stable pagination and identity.
2. Exercise weekly selected weekdays, monthly last-day, yearly selectors, local dates, and fixed UTC schedules.
3. Add, remove, move, and lifecycle-override occurrences; inspect immutable revisions and lineage.
4. Apply one, following, and whole-series edits, including a count-bounded split.
5. Author every hour during the six hours before an event, inspect six opportunities, materialize, and replay an overlapping range without duplicate work.
6. Author every-day-at-08:00-local notification cadence and verify wall-clock behavior through DST.
7. Target every occurrence and one selected occurrence; verify current provenance is required before work is authorized.
8. Edit recurrence, reschedule a target, change routing, disable a policy, and end the parent lifecycle; verify unstarted-work reconciliation and immutable started history.
9. Process materialized work through Tickerd and fake OpenClaw; inspect success, retryable failure, permanent failure, idempotency, and attempt evidence.
10. Consider a real OpenClaw canary only as a separate explicitly approved operation after all fake-path evidence is clean.

## Exit Criteria

The fat slice is ready for one environment patch only when all of the following are true:

- Every accepted recurrence and notification schedule surface is implemented across core logic, persistence, services, commands, responses, and tests.
- Equivalent commands on fresh ledgers produce byte-identical identities, hashes, order, cursors, effects, and receipts.
- Recurrence-bound work and side effects fail closed without active current occurrence provenance.
- Notification cadence and delivery retry remain observably distinct.
- Every adapter attempt is recorded in `side_effect_attempts` before the external boundary.
- The complete tests, strict type checks, focused style checks, official schema validation, computed vectors, migration rehearsals, and fake canary pass.
- The operator guide provides exact inspection, migration, rollback, and bounded canary instructions.
- No external send or deployment has occurred during implementation verification.

## Internal Gates

| Gate | Proof | State |
|---|---|---|
| Engine | Pure recurrence and notification normalization/expansion tests and computed vectors | Passed |
| Ledger | Schema-8 constraints, v6-to-v8 migration, preflight, and rollback tests | Passed |
| Commands | Authoring, reads, mutation, replay, cursor, and provenance tests | Passed |
| Notifications | Opportunity, materialization, reconciliation, and recurrence-binding tests | Passed |
| Delivery | Tickerd observe-only and active fake OpenClaw with durable attempts | Passed |
| Handoff | Full no-skip suite, documentation, migration rehearsal, and bounded fake canary | Passed |

## Deferred Beyond This Delivery

- governance-authority approval integration.
- Calendar and vendor adapters beyond the OpenClaw path.
- General daemon ownership in Spine; Tickerd remains the runtime owner.
- Conversational parsing as canonical truth; ingest must persist explicit structured facts.
- Dashboards and broad external projections.
- Release freeze-manifest promotion.

## Next Initiative: Operational Resilience and Boundedness

`specs/operational-resilience.md` is the draft authority for the next sustaining
initiative. It converts the storage-growth incident and the broader runtime sweep into
one cross-cutting contract without moving notification semantics into Tickerd or
granting automatic deletion authority over the ledger.

The planned delivery order is:

1. **Containment:** wire process-enforced Tickerd event-file limits at every Spine sink;
   retain host rotation/quota as defense in depth; expose storage pressure; validate
   retry configuration; implement `spine.tickerd-compatibility.v1` against Tickerd
   `0.2.0`, capability `tickerd.runtime-capabilities.v1`, and audited revision
   `ffe613c65ea3d6fc70a1dc3603c32068f06350df`; report that exact dependency; and add a transitional
   fail-closed dry-run size ceiling.
2. **Recovery:** isolate poison-item reconciliation failures; add bounded backoff,
   circuit breaking, and retry exhaustion; define in-progress lease recovery and
   ambiguous external outcomes through an accepted decision, ontology amendment,
   migration, readback, and operator workflow.
3. **Scalability:** replace full-fetch and count/offset automatic discovery with fair
   keyset traversal; make notification materialization continuation-complete; bound
   agenda/readback computation; and enforce request, text, collection, and expansion
   budgets at the core boundary.
4. **Qualification:** run the required idle/backlog/provider-outage/crash/tzdb/WAL/disk-
   pressure/large-ledger scenarios before declaring conformance.

This initiative does not subsume the future ledger-storage lifecycle below. It adds
budgets, alarms, stop conditions, and classification; archival or compaction still
requires its own explicit authority and recovery proof.

Runtime `0.2.0` completes the Tickerd compatibility portion of containment: exact
package/capability admission, `system.info.v2`, bounded worker event sinks, pre-cycle
storage pressure stops, and a process-local durability latch. Retry-budget validation,
the transitional dry-run ceiling, broader storage readback, and the recovery/scalability
items remain future slices.

### Future Horizon: Bounded Ledger Storage Lifecycle

Spine's ledger is canonical, append-oriented coordination evidence, so its storage
lifecycle must not be treated as ordinary log rotation. The recent scheduler no-op
suppression removes accidental idle growth; the remaining legitimate growth should be
measured in staging before retention or archival policy is designed. This horizon item
does not authorize automatic deletion, compaction, or archival.

The future work should proceed in this order:

1. Establish a post-fix storage baseline and a supported storage readback that reports
   database, WAL, table, index, and major evidence-family growth without requiring raw
   SQL from operators.
2. Classify every durable fact family as permanent canonical truth, replay/audit
   evidence, reconstructable derived data, archive-eligible evidence after semantic
   closure, or prohibited ephemeral telemetry.
3. Resolve the idempotency boundary before pruning command receipts: either preserve
   indefinite replay evidence or define a finite replay window backed by a compact,
   durable replay fingerprint or tombstone contract.
4. Specify explicit archival and compaction operations with immutable manifests,
   content hashes, verification, restore/readback behavior, and fail-closed handling.
   Delivery attempts and other safety evidence remain durable unless a normative
   retention rule proves otherwise.
5. Add disk budgets, growth alarms, and operator stop conditions. Spine must never
   automatically delete canonical evidence merely because a storage threshold is
   crossed.

Backups protect recovery but do not reduce the active ledger. WAL checkpointing only
controls the WAL sidecar, and `VACUUM` only reclaims pages after an independently
authorized retention operation. Rotating whole database files is not an acceptable
substitute because it would fragment Spine's canonical authority.
