# Decision 0004: Versioned Item Facets

Status: Proposed — specification only; not an implemented capability
Date: 2026-09-07

## Context

Archetypes classify coordination items but intentionally do not create subclasses.
A flight needs airline and flight-number facts; a lesson may need an instructor.
Encoding every domain in core tables couples Spine to particular applications.
Unregistered JSON attribute bags, however, sacrifice validation, versioning, and
reliable readback. Packs need a way to distribute structure without owning user data.

## Proposed decision

Spine will own a generic registry of immutable facet-schema revisions and canonical
facet values attached to item versions, as specified in [archetype-facets.md](../archetype-facets.md).
An owner-scoped archetype binding permits a particular schema revision on an item;
it does not instantiate values or reinterpret previously stored data.

Packs may distribute portable schema definitions and binding intentions. Installation
uses Spine commands and resolves local ownership and IDs. Packs neither execute
validators nor store operational item values. This decision does not revise the
existing pack manifest or authorize a pack installer implementation.

Promote a concept into core only when it supplies shared coordination semantics
(identity, lifecycle, time, location, relationships, permissions, notification or work
eligibility) that generic commands must enforce. Popularity alone is insufficient.
Domain description remains a facet; departure time remains a temporal fact.
Facet values MUST NOT become hidden schedule anchors, delivery destinations,
permission rules, executable instructions, or an alternative lifecycle engine.

External observations such as a current gate, delay, or forecast remain separate
provenance-bearing observations. Importing one as canonical user-approved data needs
an explicit future acceptance contract; background enrichment cannot overwrite facets.

## Consequences

- Existing items need no facets and retain their behavior.
- Every value has an exact schema revision, authoring evidence, and item version.
- Schema evolution never mutates existing values or validates old values against a
  floating latest schema. Explicit replacement is required for upgrades.
- Item read/edit permissions cover values. Catalog administration/use is separate;
  schema authors gain no access to items that use their schemas.
- The first implementation must bound schema complexity, validation, persistence,
  and queries. It must not scan all JSON blobs to answer a filter.
- Flight details are the first proof, not a built-in flight-specific database model.
- Workflow recipes, live observations, occurrence-specific facets, and protected
  advisory execution remain separate initiatives.

## Ratification gate

Review this decision with the companion specification. Ratification and machine
contract/fixture publication precede runtime implementation. This draft changes no
runtime version, schema version, or advertised command registry.
