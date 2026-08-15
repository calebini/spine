# Spine Specs

This directory contains Spine's normative design and compatibility promises.

Current spec surface:

- `overview.md`: purpose, doctrine, ontology, and non-goals
- `architecture.md`: component boundaries and relationships to tickerd, Foreman/Threshold, adapters, and projections
- `ontology.md`: first durable ontology and data model sketch
- `recurrence.md`: canonical flexible recurrence-set model, deterministic expansion and identity, mutation, and occurrence provenance
- `schedule-create.md`: implemented atomic operator-facing creation of one scheduled event/task, initial reminder policies, and optional bounded work
- `schedule-show.md`: implemented canonical readback of current schedule, notification, work, route, and delivery-attempt evidence
- `agent-command-contract.md`: draft agent-facing command/request contract for authoring and inspecting Spine coordination truth
- `SPINE_SPEC_VERSIONING_AND_FREEZE_POLICY.md`: lightweight policy for spec versions, runtime declarations, and one-way freeze-manifest pinning
- `decisions/0001-kinflow-is-donor-not-foundation.md`: accepted decision on the Kinflow relationship
- `decisions/0002-first-class-delivery-targets.md`: accepted decision separating subject/group identity from delivery endpoints

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

Spec status labels:

- Draft: useful for design and implementation planning, but not yet version-pinned as a compatibility contract
- Accepted: a ratified decision or policy that future changes should explicitly supersede
- Canonical: version-pinned behavior with matching contracts or tests

Spine is currently in seed-spec phase, so the active documents are Draft or Accepted.
