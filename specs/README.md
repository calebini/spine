# Spine Specs

This directory contains Spine's normative design and compatibility promises.

Current spec surface:

- `overview.md`: purpose, doctrine, ontology, and non-goals
- `architecture.md`: component boundaries and relationships to tickerd, Foreman/Threshold, adapters, and projections
- `ontology.md`: first durable ontology and data model sketch
- `agent-command-contract.md`: draft agent-facing command/request contract for authoring and inspecting Spine coordination truth
- `SPINE_SPEC_VERSIONING_AND_FREEZE_POLICY.md`: lightweight policy for spec versions, runtime declarations, and one-way freeze-manifest pinning
- `decisions/0001-kinflow-is-donor-not-foundation.md`: accepted decision on the Kinflow relationship

Executable contract artifacts:

- `../contracts/command-fixture-manifest.json`: manifest for MVP golden command responses
- `../contracts/schemas/command-response.schema.json`: shared command response envelope schema
- `../tests/fixtures/command_responses/mvp/`: golden MVP command response examples

Spec status labels:

- Draft: useful for design and implementation planning, but not yet version-pinned as a compatibility contract
- Accepted: a ratified decision or policy that future changes should explicitly supersede
- Canonical: version-pinned behavior with matching contracts or tests

Spine is currently in seed-spec phase, so the active documents are Draft or Accepted.
