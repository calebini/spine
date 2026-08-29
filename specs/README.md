# Spine Specs

This directory contains Spine's normative design and compatibility promises.

Current spec surface:

- `overview.md`: purpose, doctrine, ontology, and non-goals
- `architecture.md`: component boundaries and relationships to tickerd, the governance authority, adapters, and projections
- `operational-resilience.md`: draft cross-cutting resource bounds, failure containment, recovery, runtime compatibility, and operational proof requirements
- `compatibility.md`: implemented exact Spine-to-Tickerd package, capability, admission, diagnostic, v2 readback, and safety-gate contract
- `ontology.md`: first durable ontology and data model sketch
- `recurrence.md`: canonical flexible recurrence-set model, deterministic expansion and identity, mutation, and occurrence provenance
- `schedule-create.md`: implemented atomic operator-facing creation of one scheduled event/task, initial reminder policies, and optional bounded work
- `schedule-show.md`: implemented canonical readback of current schedule, notification, work, route, and delivery-attempt evidence
- `schedule-operator-tools.md`: implemented relative-event countdown request building and compact schedule operator projections
- `schedule-operations.md`: implemented cross-item agenda, atomic whole-schedule update, terminal cancellation, and mandatory notification-work reconciliation
- `relative-temporal-bindings.md`: implemented schema-8 cross-item temporal bindings, bounded discovery/reconciliation, and atomic related-task creation
- `contextual-advisories.md`: draft role-based cross-system contract for one scheduled, governed, read-only agent advisory and at most one derivative notification
- `schedule-primary-location.md`: implemented primary-location authoring, mutation, readback, builder pass-through, and operator projections on scheduled events and tasks
- `notification-rendering.md`: implemented schema-9 deterministic ordinary-reminder prose and immutable per-attempt rendering evidence
- `notification-profiles.md`: implemented dynamic item-archetype catalog, reusable versioned notification profiles, deterministic scoped defaults, and snapshot application
- `owner-scope-discovery.md`: implemented bounded read contract for discovering canonical system, subject, and subject-group owner scopes without raw SQL
- `agent-command-contract.md`: draft agent-facing command/request contract for authoring and inspecting Spine coordination truth
- `SPINE_SPEC_VERSIONING_AND_FREEZE_POLICY.md`: lightweight policy for spec versions, runtime declarations, and one-way freeze-manifest pinning
- `decisions/0001-kinflow-is-donor-not-foundation.md`: accepted decision on the Kinflow relationship
- `decisions/0002-first-class-delivery-targets.md`: accepted decision separating subject/group identity from delivery endpoints
- `decisions/0003-role-based-governance-boundary.md`: proposed decision keeping component and product names out of cross-system authority contracts

Executable contract artifacts:

- `../contracts/command-fixture-manifest.json`: manifest for MVP golden command responses
- `../contracts/schemas/command-response.schema.json`: shared command response envelope schema
- `../tests/fixtures/command_responses/mvp/`: golden MVP command response examples
- `../contracts/recurrence-fixture-manifest.json`: flexible recurrence contract fixture index
- `../contracts/schemas/recurrence-*.schema.json`: recurrence authoring, normalized-set, command, and occurrence-response schemas
- `../tests/fixtures/recurrence/contracts/`: initial flexible recurrence contract examples
- `../contracts/schedule-create-fixture-manifest.json`: atomic schedule-create structural fixture index
- `../contracts/schemas/schedule-create-*.schema.json`: atomic schedule-create request and response schemas
- `../tests/fixtures/schedule_create/contracts/`: initial atomic schedule-create structural examples
- `../contracts/schemas/schedule-show-*.schema.json`: canonical schedule-readback request and response contracts
- `../contracts/schemas/schedule-countdown-builder-*.schema.json`: deterministic relative-event countdown builder request and response contracts
- `../contracts/schemas/schedule-compact-response.schema.json`: compact schedule create/readback operator projection
- `../contracts/schedule-operator-fixture-manifest.json`: relative-countdown builder fixture index
- `../tests/fixtures/schedule_operator/`: checked-in operator-builder request examples
- `../contracts/schedule-operations-fixture-manifest.json`: implemented operational-lifecycle structural fixture index
- `../contracts/schemas/schedule-operations-types.schema.json`: shared operational-lifecycle machine types
- `../contracts/schemas/schedule-{agenda,update,cancel}-*.schema.json`: implemented agenda/update/cancel request and response contracts
- `../contracts/schemas/schedule-operation-failure-*.schema.json`: shared failure-response and state-aware semantic-failure scenario contracts
- `../tests/fixtures/schedule_operations/contracts/`: operational-lifecycle structural examples and no-mutation failure scenarios
- `../contracts/schedule-primary-location-fixture-manifest.json`: primary-location schedule contract fixture index
- `../contracts/schemas/schedule-primary-location-types.schema.json`: shared closed authoring, read view, and update-change types
- `../tests/fixtures/schedule_primary_location/contracts/`: primary-location structural examples and missing-reference scenario
- `../contracts/relative-temporal-binding-fixture-manifest.json`: relative-temporal-binding structural fixture index
- `../contracts/schemas/relative-temporal-binding-types.schema.json`: shared binding, revision, state, and readback types
- `../contracts/schemas/schedule-{related-task-create,binding-list,binding-reconcile}-*.schema.json`: implemented binding-family request and response contracts
- `../tests/fixtures/relative_temporal_bindings/contracts/`: initial binding-family structural examples
- `../contracts/spine-tickerd-compatibility.v1.json`: exact Tickerd provider baseline and Spine consumer requirements
- `../contracts/schemas/spine-tickerd-compatibility.schema.json`: machine validation for the compatibility agreement
- `../contracts/schemas/runtime-dependency-failure.schema.json`: planned fail-closed worker dependency diagnostic
- `../contracts/schemas/system-info-response-v2.schema.json`: implemented exact dependency-readback shape
- `../contracts/schemas/storage-safety-facts.schema.json`: bounded Spine facts carried by Tickerd's generic safety-stop envelope
- `../tests/contract/test_tickerd_compatibility_contract.py`: cross-repository compatibility and public-shape checks

Spec status labels:

- Draft: useful for design and implementation planning, but not yet version-pinned as a compatibility contract
- Accepted: a ratified decision or policy that future changes should explicitly supersede
- Canonical: version-pinned behavior with matching contracts or tests

Spine is currently in seed-spec phase, so the active documents are Draft or Accepted.
