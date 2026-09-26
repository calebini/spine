# Decision 0004: Versioned Item Facets

Status: Accepted — logical architecture ratified 2026-09-24; physical storage design accepted 2026-09-25; runtime implementation pending
Date: 2026-09-07
Accepted: 2026-09-24

## Context

Archetypes classify coordination items but intentionally do not create subclasses.
A flight needs airline and flight-number facts; a lesson may need an instructor.
Encoding every domain in core tables couples Spine to particular applications.
Unregistered JSON attribute bags, however, sacrifice validation, versioning, and
reliable readback. Packs need a way to distribute structure without owning user data.

## Decision

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

## Ratification and implementation gates

The operator ratified this logical model on 2026-09-24 after reviewing its evolution,
operational and usability trade-offs. Acceptance establishes the generic registry,
immutable revision, explicit binding, versioned value and core-versus-facet boundaries
above. That initial ratification did not select a physical SQL representation.

In a subsequent clarification on 2026-09-24, the operator also confirmed the logical
specification's initial scope: scalar-only fields, same-owner archetype/schema bindings,
optional facets, item/series-level values, and separate item creation then facet
attachment. Location references require existence and applicable read permission,
without introducing location retirement; subject lifecycle checks remain. Item facet
queries use subject/group item ownership, independently of schema catalog ownership.
Those clarifications did not themselves accept the physical layout or authorize runtime work.

On 2026-09-25, the operator separately accepted the hybrid physical layout in
[archetype-facet-storage.md](../archetype-facet-storage.md), v1.0: relational
identity/history and references, canonical JSON definitions/values, and derived
current-only typed indexes. This ratification does not authorize runtime work.

Before runtime implementation, codify the accepted storage design's exact DDL,
object manifest and migration fixtures. The logical specification's 2026-09-26
amendment supplies permission resolver mappings, authenticated cursor behavior and
notification-work freshness contracts with test-only machine oracles. Review those
additions and prove their persisted/concurrent runtime behavior during implementation;
static decisions do not satisfy those tests. This decision changes no
runtime version, schema version or advertised command registry by itself.
