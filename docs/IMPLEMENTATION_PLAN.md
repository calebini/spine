# Spine Implementation Plan

Status: Atomic scheduling plus canonical `schedule.show` readback acceptance verified
Last reconciled with repository state: 2026-08-15

This is a non-normative delivery plan. The specifications and machine-readable contracts remain authoritative.

## Delivered Fat Slice: Atomic Schedule Creation

The audited `spine.schedule-create.v1` contract is implemented as one environment-sized delivery. The operator-facing `schedule.create` command creates an event or task, its local-instant anchor, optional inherited recurrence, complete initial reminder-policy set, optional occurrence provenance, and optional bounded notification work in one transaction and returns one replay-safe composite receipt.

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

No schema migration is planned: schema 7 already owns every canonical row required by this orchestration. A migration is introduced only if implementation proves that a required invariant cannot be represented safely by the existing relational contract.

## Delivered P0: Canonical Schedule Verification

The `spine.schedule-show.v1` read model is implemented as the operator verification boundary over schema 7. It returns current item and schedule facts, concrete timezone-version and UTC-resolution evidence, recurrence, current notification policies and intent IDs, bounded work and attempt detail, route snapshots, complete status counts, and separate authored/opportunity/work/delivery lifecycle dimensions. The direct CLI `--item-id` and `--include` form maps to the same transport-neutral command request.

The related documentation audit treats `notification_policies.policy_id` and the public `notification_policy_id` alias as distinct intentional surfaces, replaces item-specific operator SQL with `schedule.show`, and documents `timezone_database_version.kind=system_current` as a one-time pin to a concrete version. Omission remains invalid and compatible replay retains the original resolved version.

## Delivery Goal

Ship one environment-sized implementation that supports the complete path from a structured recurrence or notification command to deterministic virtual results, canonical relational state, durable notification work, Tickerd processing, and a recorded adapter attempt.

The delivery is intentionally broad because recurrence identity, occurrence provenance, notification scheduling, reconciliation, and work authorization are one connected system. Internal gates isolate faults; they are not separate deployment units.

## Authority Map

- `specs/recurrence.md`: recurrence normalization, identity, expansion, mutation, lineage, and occurrence provenance.
- `specs/notifications.md`: notification schedules, opportunities, late handling, materialization, and reconciliation.
- `specs/ontology.md`: relational authority and lifecycle invariants.
- `specs/agent-command-contract.md`: public command and receipt behavior.
- `specs/schedule-show.md`: canonical aggregate schedule and delivery-lifecycle readback.
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

- Schema version 7 recurrence sets, immutable revisions, segments, rules, selectors, rdates, exdates, overrides, and lineage.
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
| Ledger | Schema-7 constraints, migration, preflight, and rollback tests | Passed |
| Commands | Authoring, reads, mutation, replay, cursor, and provenance tests | Passed |
| Notifications | Opportunity, materialization, reconciliation, and recurrence-binding tests | Passed |
| Delivery | Tickerd observe-only and active fake OpenClaw with durable attempts | Passed |
| Handoff | Full no-skip suite, documentation, migration rehearsal, and bounded fake canary | Passed |

## Deferred Beyond This Delivery

- Foreman/Threshold approval integration.
- Calendar and vendor adapters beyond the OpenClaw path.
- General daemon ownership in Spine; Tickerd remains the runtime owner.
- Conversational parsing as canonical truth; ingest must persist explicit structured facts.
- Dashboards and broad external projections.
- Release freeze-manifest promotion.
