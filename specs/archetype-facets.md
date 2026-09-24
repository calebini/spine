# Spine Archetype Facets

Status: Draft v0.5 — initial scope confirmed; reference/query clarifications applied; not implemented
Date: 2026-09-07
Updated: 2026-09-24
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

This document remains the logical facet owner. Physical persistence, table/constraint
inventories, typed indexes, migration/rollback and storage fixtures are delegated to
[archetype-facet-storage.md](archetype-facet-storage.md), under the Spine-wide
[storage and atomicity owner](STORAGE_ATOMICITY_SPEC.md). That leaf is a proposed
physical design, not implementation or closure of the remaining gates in Section 9.

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
| `integer` | Canonical signed decimal string: either `0` or an optional ASCII minus sign followed by an ASCII digit `1`–`9` and zero or more ASCII digits `0`–`9`. Leading zeros, plus signs and negative zero are forbidden. Inclusive declared min/max use the same encoding and stay within signed 64-bit range. |
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

### 3.1 Produced-row identity registry

The following is the complete proposed identity mapping for the facet commands in
Section 4. It extends the owning-contract registry in `agent-command-contract.md`
Section 4; it does not add commands to the current runtime registry. The generated
encoding is `<prefix>_<sha256>` over `spine.canonical-json.v1` with exactly
`derivation_version=spine.command-id.v1`, the canonical `command`, caller `command_id`,
`row_role`, and `request_path`. Prefixes below exclude the separating underscore.
Paths are fixed logical production paths, not caller-selectable JSON pointers;
payload nesting, transport envelopes and input array ordering do not alter them.

| Producing branch / artifact | Identity field or composite key | row_role | Prefix | request_path |
| --- | --- | --- | --- | --- |
| `facet_schema.create`: new root | `facet_schema_id` | `facet_schema` | `facet_schema` | `/facet_schema` |
| `facet_schema.create`: first revision | `facet_schema_revision_id` | `facet_schema_revision` | `facet_schema_revision` | `/facet_schema/revision` |
| Changed `facet_schema.publish`: new revision | `facet_schema_revision_id` | `facet_schema_revision` | `facet_schema_revision` | `/facet_schema/revision` |
| Changed `item_archetype.facet_binding.set`: new/replacement binding | `facet_binding_id` | `archetype_facet_binding` | `archetype_facet_binding` | `/facet_binding` |
| Changed `item.facets.update`: item version and complete snapshot | `(item_id, item_version)` | none | none | none |
| Snapshot entry, newly set or copied forward | `(item_id, item_version, facet_key)` | none | none | none |
| Every changed facet write: one audit row | `audit_id` | `audit` | `audit` | `/audit` |
| Every fresh successful facet write, including no-op: one receipt | `command_receipt_id` | `command_receipt` | `command_receipt` | `/` |

The three new roles are reserved by this proposed registry; `audit` and
`command_receipt` reuse the existing common roles. No other generated facet row IDs
are permitted. Before runtime advertisement, executable role registration and golden
preimage/digest fixtures MUST match this table exactly.

A new root's first revision_number is `1`; a changed publish uses previous+1 in
the same transaction and retains the root ID; revision numbers are never caller-selected.
Retirement retains root and revision
IDs; it produces only the changed-write audit and receipt, not a new revision.
Binding replacement retains the prior binding as superseded and creates the one new
binding above. Binding remove retires the existing binding ID without producing a
replacement or tombstone binding; an absent-binding no-op produces only a receipt.

For an item update, a changed `set` entry points to that command's receipt as its
source authoring receipt. Retained entries, including a structurally identical `set` in an
otherwise changed batch, preserve their prior source receipt, schema/binding IDs and
archetype evidence. Entry equality compares normalized values, schema revision, binding
and archetype evidence, excluding the source receipt and composite version key. Changing
a schema revision or binding is therefore a changed entry even when values are equal. Copy-forward changes the composite item-version key, not those
source facts. There is no separate generated value ID or authoring-row ID. A remove
omits the entry from the new snapshot; prior snapshots remain intact, and the command
receipt records the removed key. No facet tombstone ID is generated. Existing generic
supporting rows continue to follow their owning copy-forward identity rules.

Definition-equivalent publishes and other successful no-ops create no domain revision,
binding, snapshot, or audit row; they create the one common fresh-command receipt.
Compatible replay creates no rows, including no second receipt. Failed commands create
none of these artifacts. These rules apply to all six facet write commands in Section 4.

## 4. Proposed command surfaces

All mutation requests use the owning proposed family, `command_id`, actor and explicit
action timestamp under the existing common command contract. Fresh requests require
the expected target revision/version. Read requests do not write receipts. Exact JSON
schemas and field spelling of common envelopes are now recorded in Section 10;
the remaining implementation gates still apply.

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
same-command replay returns recorded stable identities with `replayed=true` and
`changed=false`, rather than producing new rows (Section 10.2).
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
New subject references require existing active subjects and applicable read permission.
New location references require existing locations and applicable read permission;
locations have no active/inactive lifecycle in this slice. No new
reference kinds or access grants arise from a field. The trusted-local CLI retains
its existing full-scope posture; HTTP requires explicit registry/resolver additions.

Item readback includes the pinned definition needed to interpret values even after
schema retirement. It does not require live use permission on that catalog. Authors
must understand this as publication of that definition to readers of the item;
definitions contain no credentials, private defaults or operational user values.
Reference targets still require current visibility. An unreadable nested reference
denies the whole facet readback, without substituting null or disclosing an ID.
Inactive subject references are preserved historically and marked inactive when readable;
they never silently disappear. A readable existing location is represented with
reference status `active`, meaning an existing usable reference, not a persisted
location lifecycle flag. No location-retirement capability is introduced. Historical
snapshots use current item access checks.

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
exact schema revision, within one explicit **item** owner scope: subject or subject_group.
The query owner does not select the schema's catalog owner. System-owned schema catalogs
remain valid, but `owner_kind=system` is rejected on item.facets.query; it means neither
unowned items nor an all-ledger search. No cross-revision inference,
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

The structural schemas, fixture manifest and pure normalization/identity vectors are
now present (Section 10). They do not satisfy the persisted-state, permission, cursor,
work-freshness, concurrency or query-plan acceptance families below. Their tests must
not be reported as proof of those runtime behaviors.

The focused machine-contract recheck completed on 2026-09-12 with
`boundary_preserved=true` and `pass_with_minor_clarification`. Its sole clarification
corrected the recheck notes' coverage wording: schema creation has one changed replay
branch, while the other five writes have changed and no-op replay branches. The
reviewer found the source schemas, manifest, fixtures and focused assertions aligned;
no source-contract patch was required. This closes the recheck gate without claiming
runtime implementation or satisfying the remaining gates below.

Required fixture families and observable oracles:

1. Definition normalization: equivalent field order yields identical hashes; unknown
   keywords, invalid bounds, oversized definitions and executable forms fail unchanged.
2. Type validation: NFC, integer boundaries, leap dates, nulls, wrong reference types,
   unknown fields and missing required fields have deterministic outcomes.
3. Revision isolation: publish leaves old snapshots byte-identical; explicit upgrade
   succeeds only against the active binding and expected item version.
4. Atomic mutation and identity: golden preimages/digests cover every generated row
   in Section 3.1; create/publish revisions differ by their command facts, and reordered
   change arrays do not change normalized identity. Two-key failure rolls back both;
   no-op preserves item version and emits only its receipt; replay emits no rows;
   retire/remove do not invent replacement IDs; copied entries retain source evidence
   under their new composite keys; same-ID conflict leaves the original receipt intact.
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

The operator confirmed the initial scope on 2026-09-24: scalar-only fields, same-owner
archetype/schema bindings, optional facets, item/series-level values rather than
per-occurrence values, and two-command initial authoring. These product choices are
settled for the initial slice. They do not ratify the physical storage draft, close
the remaining engineering gates, or advertise implemented capabilities.

## 10. Machine-contract codification (draft)

The repository-only proposed registry is
`contracts/archetype-facet-contract-registry.v1.json`. It maps all eleven commands to
their exact request/response schema fragments and family versions. It is not imported
by runtime preflight, CLI dispatch, package capability declarations or the web allowlist.
The five `contracts/schemas/archetype-facet-*.schema.json` files define types, requests,
successes, handler failures and the fixture-manifest structure. The fixture manifest is
`contracts/archetype-facet-fixture-manifest.json`; fixtures and pure vectors live under
`tests/fixtures/archetype_facets/`. These are draft contracts, not an installed feature.

### 10.1 Wire choices

The canonical command is supplied by the transport route, not duplicated inside its
request. Each request requires the exact owning `contract_version`. Writes require
`command_id`, `actor_subject_id`, `action_timestamp_utc` (whole-second UTC `Z` form).
Requests are closed: unknown properties fail. Read requests carry no write identity.
IDs use the existing nonempty-string ID domain; generated IDs must additionally obey
Section 3.1, as checked by identity vectors rather than invented by a caller.

Definitions are passed as `definition`, with `fields` an array of declarations using
`key`, `type`, `required`, optional `queryable`, and type-specific properties.
`max_length`, integer `min`/`max`, revision/item versions and page limits are canonical
decimal strings, not JSON numbers. Integer bounds are both required. Display metadata
uses the existing catalog lengths: display_name 1–160 code points, description null
or 1–2000 code points. NFC normalization precedes length and byte checks. Text controls
mean U+0000–U+001F and U+007F–U+009F; unpaired surrogates are rejected everywhere.
The exact definition preimage is
`{derivation_version: "spine.facet-definition.v1", definition: <normalized definition>}`.
The 32 KiB definition bound measures that normalized definition, not its enclosing
hash preimage. The 64 KiB values bound measures a canonical object mapping each
facet_key to its values object; per-entry provenance/definitions are not included.
Each individual values object remains limited to 16 KiB.

Publish/retire use `expected_current_revision_id`. Binding set/remove require
`expected_binding_id`, including explicit null for no active binding. A missing active
binding with a non-null expectation is a conflict, not the absent-remove no-op.
Item updates use `expected_item_version`; optional historical read selection uses
`item_version`. A `set` requires `expected_binding_id` non-null; its values are a full
replacement. Duplicate declaration/change/entry keys are semantic errors, even when
the array elements differ structurally. Arbitrary scalar strings in the envelope are
not authorization to bypass the exact pinned field type and declaration constraints.

### 10.2 Success, failure and readback

Successes contain `response_contract` equal to the command's owning family. Every
write response includes `command_id`, `command_receipt_id`, the closed `effect`,
`changed` and `replayed`. Fresh outcomes use `replayed=false`: changed writes include
`audit_id`, while fresh no-ops forbid it. Compatible replay uses `replayed=true` and
`changed=false`, creates no rows, and returns the stored receipt ID, effect and stable
result identities. An original changed effect requires its stored `audit_id`; an
original no-op effect forbids that field. On replay this is historical audit evidence,
never evidence of a newly performed write. The effect names the stored receipt's
outcome; it does not override the current invocation's changed=false result.

These replay branches apply to all six writes, including create, retire and remove,
and replay of both changed and no-op outcomes. Prior/resulting version and binding
facts stay exactly as recorded, even if the target has since advanced; replay is not
a current-state read. For `item.facets.update`, replay returns
`changed_facet_keys=[]` and `reconciliation_performed=false`, regardless of the
original values of those two invocation-activity fields. It neither reconciles work
nor advances a version. `replayed` and the activity-field substitutions are response
projection facts only: they do not rewrite the receipt, semantic hash, stored effect,
or command-derived identities. Section 4's current disclosure checks still apply.

Catalog receipts report `prior_revision_id`, `facet_schema_revision_id` and
`revision_number`; create has prior=null and number=1. Publish increments only on
change; retire and no-op preserve the revision. Binding set reports prior/resulting
IDs and schema revision. Remove reports the same retired binding ID as prior/result;
the absent-remove no-op reports both IDs as null. Item receipts report prior/resulting
item versions and sorted `changed_facet_keys` (empty on no-op or replay). Fresh changed
versions advance by one; replay preserves the original version pair.
`reconciliation_performed` reports whether work reconciliation ran on this invocation;
no-op and replay require false. The sample changed receipt is for an item with no policies or
work and uses false. This boolean does not resolve or claim safety for queued, leased
or attempted work. Section 5 remains a blocking integration gate.

Schema show returns a `root` and selected immutable `revision`; the selected revision
must belong to that root, but can differ from its current pointer. Stored definitions
are fully normalized, including explicit queryable=false. Item show returns sorted
`entries`; each contains the pinned schema revision/definition/hash, facet binding ID,
`archetype` assignment evidence (root/revision, selection_source and source_ref when
present), values, `source_command_receipt_id`, and `references` sorted by field key.
Reference state contains exactly one entry for every reference-valued field present.
Its ID/kind must agree with the pinned definition and value. An unreadable reference
denies the whole result; inactive but readable subject references are returned as
inactive. Existing readable location references always return status=active under
Section 6; no location-status column is required or inferred.
An empty snapshot returns entries=[], not null or an omitted field.

Handler failures use the existing ok/command/error envelope. The proposed facet
domain reasons in Section 4 are carried as `error.code`; exact CLI exit mappings are
in the draft registry. Definition/value errors use exit 2, binding/archetype conflicts
6, retired-schema use 2, and missing/unreadable references or inactive subjects uniformly 4 with
`facet_reference_unavailable`. Paths identify fields but never echo private values.
Admission/permission and operational-capacity envelopes remain owned by their adapters;
the facet handler schema does not replace or freeze them. Resolver mappings, admission
ordering and the exact capacity wrapper remain pre-implementation gates. Fixture error
messages are illustrative safe prose, not byte-exact public message constants.

### 10.3 Pagination and validation limits

Catalog list defaults status=active and limit=25; explicit status selects active or
retired. Binding list returns only active bindings. Query returns current matching
item IDs/versions. All pages include the accepted decimal-string limit, `has_more`
and `next_cursor`; has_more=false requires null, true requires a nonempty opaque
cursor at most 4096 characters. Returned collection length cannot exceed limit.
Root IDs, facet keys and item IDs respectively determine the existing total order.

Only the opaque cursor envelope is specified here. Token encoding, authenticated
binding, snapshot identity, expiry and access-epoch sources still require the dedicated
cursor contract before runtime. No fixture with an arbitrary token proves pagination
security or freshness. Likewise, JSON Schema checks structure, not NFC, declared-field
validation, hash correctness, foreign-key visibility, byte ceilings or transactional
invariants. Test-only pure oracles cover selected semantic vectors; no application
validator, database migration, index or command handler is introduced by this bundle.
