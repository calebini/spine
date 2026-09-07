# Spine Archetype Facets

Status: Draft v0.1 — proposed contract, not implemented or audited
Date: 2026-09-07
Scope: Registered typed item facts, immutable schema revisions, archetype bindings,
bounded authoring/readback, and a flight-details proof

## 1. Purpose and authority

An archetype says what an item represents; a facet stores typed facts about it.
`flight` remains an event archetype. An optional `flight_details` facet can hold
airline, flight number, and origin/destination references without a flight table.

The boundary is [Decision 0004](decisions/0004-versioned-item-facets.md). This draft
depends on `ontology.md`, `notification-profiles.md`, `permissions.md`,
`agent-command-contract.md`, `operational-resilience.md`, and the schedule contracts.
Core time, location, relationships, lifecycle, ownership, notifications, and work
remain authoritative. Facets cannot override or implicitly drive those mechanisms.

Proposed families are `spine.facet-schemas.v1`, `spine.archetype-facet-bindings.v1`,
`spine.item-facets.v1`, and `spine.item-facet-query.v1`. These names are reservations
in this draft, not advertised capabilities. Current closed CLI/HTTP schemas do not
accept facet fields. No runtime or migration is included in this specification task.

## 2. Model and invariants

### 2.1 Schema roots and revisions

A schema root has an immutable `facet_schema_id`, owner scope, owner-local
`schema_key`, current revision pointer, and status `active` or `retired`.
Owner kinds follow existing catalog scopes: system, subject, subject_group. There is
no built-in domain taxonomy. Keys are lowercase ASCII `[a-z][a-z0-9_]{0,63}`.
The pair (owner scope, schema_key) is unique, including retired roots; keys are not
recycled. Retirement is terminal in this slice.

A revision has `facet_schema_revision_id`, schema root ID, positive decimal-string
`revision_number`, `display_name`, nullable `description`, compatible item types
(nonempty subset of event/task), closed field declarations, and `definition_hash`.
The exact revision owns validation and query declarations. Revisions are immutable;
even description changes publish a new revision. The current pointer is a catalog
convenience, never a value-validation input. `flight_details.v1` in prose means the
first published definition, not a globally reserved key or a floating lookup alias.

### 2.2 Archetype bindings

An active binding associates an exact archetype root with an exact schema revision
and a `facet_key`. At most one active binding exists per (archetype ID, facet_key).
The archetype and schema must have the same catalog owner in v1. Publishing a schema
revision does not move bindings. Explicit binding set supersedes the previous binding;
remove retires it. Compare the expected prior binding ID (null for first creation).
Bindings are optional eligibility declarations, not required data, defaults, or
automatic facet creation. Schema and archetype compatible item types must intersect.

### 2.3 Item values

A complete facet snapshot belongs to `(item_id, item_version)` and contains at most
eight entries, unique by `facet_key`. Each entry records the exact schema revision,
binding ID, archetype assignment evidence, canonical values, and source authoring
receipt. Existing items begin with an empty snapshot. Absence differs from an empty
object. Field nulls are forbidden; remove an optional field by omitting it in a full
replacement. Missing required fields fail validation.

Unrelated item edits copy the snapshot forward exactly. Catalog edits, retirement,
or binding changes do not rewrite it. Historical values remain decodable using their
stored immutable schema revision. A value replacement requires the current active
binding and active schema/archetype, including when upgrading an old revision.
An unchanged retained entry need not requalify against current catalog status.

Changing or clearing an item's archetype while retaining a nonempty facet snapshot
fails `facet_archetype_conflict`; callers must explicitly clear facets first in this
initial slice. No command silently deletes data. Removing facets remains possible
after catalog retirement. Facets apply to the series item, not individual recurrence
occurrences; per-occurrence values are out of scope.

## 3. Closed type system and normalization

V1 uses a small declarative field language, not arbitrary executable JSON Schema.
Each field has a key in the same ASCII key domain, a boolean `required`, and one type:

| Type | Value and validation |
| --- | --- |
| `text` | Nonempty NFC string, no control characters; declared `max_length` 1–1024 Unicode code points. Whitespace is preserved, not trimmed. |
| `enum` | One exact string from 1–64 unique NFC choices, each 1–128 code points. Case-sensitive. |
| `boolean` | JSON true/false, without string/number coercion. |
| `integer` | Canonical signed decimal string, no leading zeros, plus sign or negative zero; inclusive declared min/max within signed 64-bit range. |
| `date` | Valid proleptic Gregorian `YYYY-MM-DD`, years 0001–9999; descriptive only, never a temporal anchor. |
| `reference` | Existing Spine `subject` or `location` ID; declaration fixes the target kind. No polymorphic object or arbitrary URI. |

Each declaration also has `queryable` (boolean, default false). Unknown schema keys,
field keys, types, coercions, floats, nulls, nested objects, arrays of values, regexes,
formulas, computed defaults, remote references and scripts are rejected. Definitions
have 1–32 fields. Full normalized definition is at most 32 KiB UTF-8 canonical JSON;
one values object at most 16 KiB; all item values together at most 64 KiB. Text is
normalized to NFC before validation/hashing; enum choices normalize then deduplicate,
with duplicate declarations rejected rather than silently collapsed.

Definition normalization fills queryable=false, orders fields by key, enum choices
lexicographically by Unicode scalar value, and compatible types lexicographically.
Integers and dates are validated, not rewritten from permissive input. Hashes use
existing `spine.canonical-json.v1` and SHA-256. `definition_hash` covers a preimage
with `derivation_version=spine.facet-definition.v1` and the entire normalized revision
definition excluding generated IDs, revision number and hash. Catalog owner is a
root fact, not part of the portable definition hash.

Root, revision, binding, and authoring-row IDs follow the existing command-derived
ID rule, with command, command_id, row_role and canonical request_path. A new revision
number is previous+1 under the same transaction; it is never caller-selected. A
definition-equivalent publish is a no-op, with no revision increment.

## 4. Proposed command surfaces

All mutation requests use the owning proposed family, `command_id`, actor and explicit
action timestamp under the existing common command contract. Fresh requests require
the expected target revision/version. Read requests do not write receipts. Exact JSON
schemas and field spelling of common envelopes must be published before implementation.

| Command | Additional request facts | Terminal effects |
| --- | --- | --- |
| `facet_schema.create` | owner, schema_key, complete definition | `facet_schema_created` |
| `facet_schema.publish` | root ID, expected current revision ID, complete definition | `facet_schema_published`, `facet_schema_publish_noop` |
| `facet_schema.retire` | root ID, expected current revision ID | `facet_schema_retired`, `facet_schema_retire_noop` |
| `facet_schema.show` | root ID; optional exact revision ID | Complete root/revision readback |
| `facet_schema.list` | one explicit owner, status filter, limit/cursor | Bounded catalog page |
| `item_archetype.facet_binding.set` | archetype ID, facet_key, exact schema revision ID, expected binding ID | `facet_binding_set`, `facet_binding_set_noop` |
| `item_archetype.facet_binding.remove` | archetype ID, facet_key, expected binding ID | `facet_binding_removed`, `facet_binding_remove_noop` |
| `item_archetype.facet_binding.list` | archetype ID, limit/cursor | Binding page |
| `item.facets.update` | item ID, expected item version, changes | `item_facets_updated`, `item_facets_update_noop` |
| `item.facets.show` | item ID; optional exact item version | Complete pinned facet snapshot |
| `item.facets.query` | owner, exact schema revision ID, field, equality value, limit/cursor | Bounded matching item IDs/versions |

`changes` contains 1–8 operations, sorted by facet_key for normalization; duplicate
keys fail. Each operation is `set` with facet_key, expected active binding ID, exact
schema revision ID and complete `values`, or `remove` with facet_key. There is no
merge/upsert of individual fields. All changes commit atomically in one new item
version. A structurally equal normalized final snapshot is a no-op; existing source
provenance is retained. Removing an absent key is a no-op. Same-value sets still
validate binding, schema and references on a fresh command. Catalog create collisions
are conflicts, not implicit overwrite or revival.

Success receipts include command/receipt IDs, effect, changed, affected root/revision
or item IDs, prior/resulting versions, and sorted changed facet keys. Compatible
same-command replay returns the recorded outcome rather than producing new rows.
Common replay semantics apply before fresh version checks, but never bypass current
disclosure authorization in a permission-enforced adapter. Same ID/different normalized
semantic request fails `semantic_conflict`. Failed validation changes no state.

Validation precedence: envelope/types/bounds; adapter admission; replay compatibility;
target visibility/existence; expected versions; active binding/catalog eligibility;
definition and value validation; reference access; final snapshot limits; transaction.
Inside the write transaction recheck versions and authority before committing.
Public errors do not reveal foreign target existence. Proposed domain reasons include
`facet_schema_invalid`, `facet_value_invalid`, `facet_binding_conflict`,
`facet_archetype_conflict`, `facet_schema_retired`, and `facet_reference_unavailable`;
use existing stale/conflict/permission/capacity envelopes where applicable. Field
errors carry paths, never echo private values. Machine error mapping is an explicit
contract-codification gate, not permission to improvise runtime strings.

## 5. Item-version and scheduling integration

Facet-only updates do not move times, re-expand recurrence, create reminder policies,
materialize work, send notifications, or invoke recipes. They still increment the
canonical item version, so they MUST use the common item-version carry-forward path
for recurrence, notification/profile, location and binding facts. They must not leave
policies attached only to an obsolete version or orphan queued work.

Before runtime implementation, fixtures MUST prove the exact existing freshness and
reconciliation behavior for queued, leased and attempted work when only facets change.
The command must report whether reconciliation was performed; it cannot claim queued
work was retained safely merely because no scheduling field changed. Any required
reconciliation follows existing notification rules and shares the command transaction.
This integration is a buildability gate, not an additional notification engine.

Initial authoring remains explicit: create the item with its archetype, then attach
facets using its returned version. This is two atomic commands, not an atomic composite;
if attachment fails, the created item remains and the operator must see that outcome.
Atomic create-with-facets may be specified later through a versioned schedule contract.
Do not add optional fields to frozen schedule or web contracts in place.

## 6. Permissions and readback

Value read/edit follows the owning item's permission model. No field-level ACL or
separate facet owner exists. Schema management and binding management require catalog
administration under the existing owner/role rules; attaching values requires schema
use permission as well as item edit. Possession of a schema ID grants neither.
New references require existing active targets and applicable read permission. No new
reference kinds or access grants arise from a field. The trusted-local CLI retains
its existing full-scope posture; HTTP requires explicit registry/resolver additions.

Item readback includes the pinned definition needed to interpret values even after
schema retirement. It does not require live use permission on that catalog. Authors
must understand this as publication of that definition to readers of the item;
definitions contain no credentials, private defaults or operational user values.
Reference targets still require current visibility. An unreadable nested reference
denies the whole facet readback, without substituting null or disclosing an ID.
Inactive references are preserved historically and marked inactive when readable;
they never silently disappear. Historical snapshots use current item access checks.

Full readback contains item/version, archetype evidence, sorted entries, exact schema
definitions and hashes, values, authoring receipts, and reference state. List/query
projections contain IDs and versions, not all facet values. The dedicated facets
surface precedes opt-in successor schedule projections. Existing `schedule.show`,
agenda, compact receipts and rendering remain unchanged until their contracts are
explicitly extended. UI labels and field ordering are presentation, not authority.

## 7. Bounded queries and persistence

Persist immutable definitions and snapshots with foreign keys, exact revision pointers,
and uniqueness constraints. Historical definitions referenced by values cannot be
deleted. Current facet values and declared queryable scalar fields have transactional
indexes updated in the same commit as the item version. Ordinary item edits must
maintain these indexes too. Indexes are derived, never a second source of truth.

V1 query supports one equality predicate against one declared queryable field of an
exact schema revision, within one explicit owner scope. No cross-revision inference,
full-text, ranges, joins, arbitrary JSON paths or user SQL. Typed normalization equals
authoring normalization; text/enum equality is case-sensitive. Query returns current
items only, ordered by item ID. Catalog list order is root ID; binding list order is
facet_key. Limits are decimal strings 1–100, default 25. Unsupported filters fail.

Permission-enforced query starts from authorized indexed candidates, not a global
JSON scan followed by filtering. Resource resolution is capped at 100 per request;
overflow fails capacity, not false completeness. Use the existing operational SQL,
elapsed-time and response-byte ceilings. Page cursors bind normalized query, selected
identity, owner, exact revision, access epoch, source snapshot and expiry. Changed
facts invalidate the cursor; never silently skip or duplicate matches. A dedicated
cursor wire contract and index/query-plan proof are required before implementation.

Reads and unsuccessful preflight write nothing durable. No daemon scans facets,
revalidates every item after schema publication, or emits idle receipts. Revision and
receipt retention follows ledger policy; this feature introduces no background growth.

## 8. Flight example

Portable schema key: `flight_details`; compatible item types: `[event]`.
Bind its first revision to the owner-local `flight` archetype using facet_key
`flight_details`. No core registry preinstalls this schema or archetype.

| Field | Declaration | Example |
| --- | --- | --- |
| airline | optional text, max_length 128, not queryable | Air Example |
| flight_number | required text, max_length 32, queryable | AX123 |
| origin | required location reference, queryable | An existing airport location ID |
| destination | required location reference, queryable | Another airport location ID |

Airport references describe the flight's endpoints; they do not replace the generic
primary location or create arrival/departure anchors. Store those times and zones in
the existing coordination model. Gate, terminal changes, delays and vendor status
are excluded from this proof. Booking references, passport data and secrets are not
part of the example. A recurring flight shares the item-level values; differing
per-occurrence flight details require separate items in this slice.

## 9. Acceptance and next gates

Before implementation, publish request/response/type schemas, a fixture manifest,
normalization/identity vectors, permission resolver mappings, a cursor contract and
a migration/index plan. No promised runtime family is advertised before executable
tests pass. Audit this draft first; then close the listed machine-contract and work
freshness gates without widening it to workflow recipes or live enrichment.

Required fixture families and observable oracles:

1. Definition normalization: equivalent field order yields identical hashes; unknown
   keywords, invalid bounds, oversized definitions and executable forms fail unchanged.
2. Type validation: NFC, integer boundaries, leap dates, nulls, wrong reference types,
   unknown fields and missing required fields have deterministic outcomes.
3. Revision isolation: publish leaves old snapshots byte-identical; explicit upgrade
   succeeds only against the active binding and expected item version.
4. Atomic mutation: two-key failure rolls back both; no-op preserves item version;
   replay adds no second revision; same-ID conflict leaves original receipt intact.
5. Lifecycle: retire prevents new attachment but permits retained reads/removal;
   archetype change with nonempty facets fails without loss.
6. Access: foreign catalogs/references deny without leakage; catalog administrator
   cannot read unrelated items; current permissions govern historical readback.
7. Scheduling: facet edit preserves time/policy meaning; queued, leased and attempted
   work outcomes follow the explicit freshness rule; no extra send occurs.
8. Queries: indexed equality, pagination invalidation, access revocation and capacity
   limits behave identically at small and large unrelated-ledger sizes; no JSON scan.
9. Concurrent writers: facet versus schedule edit has one winner and a stale conflict,
   not lost fields, half-updated indexes or premature nested transaction commits.
10. Flight proof: register, bind, attach, inspect, query and replace through commands;
    location/time authority and existing notification behavior remain unchanged.

Draft decisions requiring review are the deliberately scalar type subset, same-owner
bindings, optional rather than mandatory facets, series-level values, and two-command
initial authoring. These are proposed defaults, not previously ratified capabilities.
