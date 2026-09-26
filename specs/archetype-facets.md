# Spine Archetype Facets

Status: Draft v0.7 — integration audit clarifications specified; not implemented
Date: 2026-09-07
Updated: 2026-09-26
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
[storage and atomicity owner](STORAGE_ATOMICITY_SPEC.md). That leaf's physical design
was accepted as v1.0 on 2026-09-25; acceptance is not implementation or closure of the
remaining gates in Section 9.

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

Every fresh `set`, including a same-value no-op, MUST require the target item's
concrete `item_type` in both the item's pinned assigned archetype revision's and
the selected pinned facet-schema revision's `compatible_item_types`. The binding's
nonempty intersection test alone is insufficient: an event/task archetype can bind
an event-only schema, but a task cannot set that facet. After active binding/catalog
eligibility and before value validation, incompatibility fails `wrong_item_type`,
`field=item_id` (CLI exit 2; admitted web domain_failure, HTTP 422). Remove-only
changes, unchanged copy-forward and compatible receipt replay do not re-run this
fresh-set test; they do not author a new value against a new schema revision.

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

Validation precedence: envelope/types/bounds; adapter admission; the private receipt
lookup and authorized replay branch in Section 6.2; for a fresh command, target/nested
authority and visibility/existence; expected versions; active binding/catalog eligibility
and concrete item-type compatibility; definition and value validation; reference access;
final snapshot limits; transaction. Reference authority is resolved before fresh domain
checks; reference lifecycle/value validation remains in the reference-access phase.
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

### 5.1 Exact facet-only work rule

Publishing/retiring a schema or changing a catalog binding does not change an item
version, its pinned definition, or any work. Explicitly upgrading an item's facet
revision is an item edit and follows the same rule as replacing/removing its values.

For a changed item.facets.update, compare the before/after notification inputs inside
the item transaction. Only facet snapshots, the item version/update evidence, and
ordinary supporting-row copy identities may differ. Core item lifecycle, title/detail,
anchors/timezones, locations, subject roles, active temporal binding meaning, recurrence
revision/hash, profile application meaning and notification intent semantics MUST match.
For each policy compare intent ID, creation facts, status, recipient, channel, route,
target, schedule hash and late handling, excluding copy-row IDs/version/authoring
timestamps/source-policy pointer. Policy sets must match by intent, including disabled
policies; never match only on eligible time. Mismatch is environment_failure and rolls
back the entire facet command; it is not permission to repair unrelated scheduling truth.

Do not create a recurrence revision or regenerate provenance for a facet-only version.
Existing recurrence resolution must still select the unchanged recurrence revision;
two or more consecutive facet edits must not break ordinary work intent resolution.
Temporal binding freshness remains owned by relative-temporal-bindings.md: editing a
source event increments its version and can make downstream follow_source bindings
stale even when its time is unchanged. Do not rewrite those bindings or dependent tasks
inside the facet command. Their normal bounded reconciliation must complete before
dependent work can pass its existing freshness gate. Facet edits on a bound target task
do not by themselves change the source version or due-anchor meaning. Thus retention
below covers this item's work, not a promise that every dependent item's work stays current.
The notification retention permission in notifications.md Section 10 is mandatory
for a proven facet-only change:

| Existing work | Effect of the facet command |
| --- | --- |
| Eligible, zero attempts and no attempt evidence | Retain the exact row, ID, nominal eligibility and original version/policy/provenance evidence; do not cancel/recreate or reschedule it |
| Leased/in-progress, including before adapter invocation | Do not release/reassign the lease or alter the row; normal attempt-start checks still apply |
| Eligible retry with attempts | Preserve work, retry budget and attempt history; ordinary retry/freshness rules still apply |
| Completed/failed/cancelled or otherwise terminal | Preserve history; do not resurrect, resend or reinterpret an already persisted rendering |
| Already stale for a reason independent of facets | Do not revive or claim deliverability; existing scheduler/worker stale-work handling remains responsible |
| No work | Create none; later ordinary bounded scheduling may materialize missing opportunities |

Retention means absence of a new facet-induced invalidation, not a delivery guarantee.
Before every attempt the worker resolves the current policy by `(item_id,
notification_intent_id)`, verifies semantic continuity against the work's original
policy and existing target/route/provenance/lifecycle checks. A one-hop
source_notification_policy_id match is insufficient after multiple copy-forwards.
Missing/ambiguous current intent fails closed. Work IDs and immutable historical FKs
are not rebound to the current version to conceal stale evidence. Other work kinds
retain their owning contracts; this rule covers ordinary notification_reminder only.

`reconciliation_performed=true` on a fresh changed command exactly when current policies
exist or any notification_reminder work exists and the transaction completed the
above equivalence check. This is reconciliation by verified retention, not cancellation
or expansion. Otherwise it is false; no-op and replay always return false. Use a bounded
indexed existence probe for work, not a scan of all attempts or exhausted work history.
No work IDs/counts are added to the facet receipt. Inability to establish equivalence
within the operation budget fails atomically, never commits an unchecked version.
External route/lifecycle changes can still cause ordinary attempt rejection; a raced
item edit must yield one committed version and one stale_version, not a lost update.

Current rendering does not consume facets. A future facet-consuming advisory must pin
its item/schema inputs and define its own acceptance freshness; it cannot infer that
ordinary reminder retention authorizes use of stale facet values. Required executable
oracles include multiple successive edits, explicit schema upgrade, recurring work,
follow_source dependencies, lease/attempt races and retry without a duplicate send.

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

### 6.1 Closed resolver mapping

The machine companion is `contracts/archetype-facet-integration.v1.json`. These are
required resolver semantics for future exposure, not additions to today's web allowlist.
Trusted-local commands keep full scope but must still enforce domain/reference existence
and active-on-authoring rules. A deployment-enforced single-operator full-scope mode
may bypass resource permissions, never catalog lifecycle or domain validation.

| Commands | Required authority in permission-enforced mode |
| --- | --- |
| facet_schema.create | Catalog administration of requested owner |
| facet_schema.publish / retire | Catalog administration of resolved root owner |
| facet_schema.show | catalog.read (catalog.use also implies read) on root |
| facet_schema.list | Authorized catalog candidates in explicit owner scope; no all-ledger listing |
| item_archetype.facet_binding.set | Catalog administration on archetype and schema, same owner, exact readable revision |
| item_archetype.facet_binding.remove | Catalog administration on archetype; no fresh use of retired schema required |
| item_archetype.facet_binding.list | catalog.read on archetype and every returned schema; inaccessible nested schemas deny the whole page |
| item.facets.update | item.edit; each fresh set additionally requires catalog.use on assigned archetype and schema, current binding, and reference checks |
| item.facets.show | Current item.read, including for historical versions; every returned reference must be visible |
| item.facets.query | catalog.read on exact schema revision plus item.read for candidate items; reference predicates require reference visibility before lookup |

Catalog administration means the selected subject owns a subject catalog, or is active
admin/owner of its adopted group. Ordinary member/creator rights do not administer
catalogs. System catalog mutation is trusted-local administration only. Catalog read/use
uses ownership, active group membership or existing explicit catalog.read/catalog.use
grants; extend the existing grant resource-kind vocabulary to facet_schema at implementation
with immutable owner revision 1. No new grant operation, implicit system-public catalog,
cross-owner binding or catalog-admin delegation is introduced. Lists return the authorized
subset in a named scope (explicit per-root grants can expose a subset of a foreign scope),
not counts of hidden roots. Item query likewise intersects its explicit owner with
authorized item candidates; foreign ownership alone is not denial of a valid item grant.
The item owner/revision comes from item_access_owners, not participants, archetype
ownership or labels. Items without an adopted owner do not match an owner-scoped query,
including trusted-local queries; exact-ID trusted-local show/update remains available.

Remove-only item edits do not require fresh catalog use or permission to follow the
removed reference. Unchanged retained entries may copy without renewed catalog/reference
use checks; this cannot disclose their values. Fresh sets, including same-value no-ops,
must pass them. Item edit does not authorize unrelated catalog writes or delivery release.
Readback of a stored definition is authorized by the item, not current catalog access.

**Reference resolver limit:** Do not invent a shared subject/location ACL here. Under
the existing trusted web subset, the selected subject can reference/read itself; other
subjects and existing locations with no explicit family-owned sharing resolver are
unavailable, even if they appear in owner discovery, another item or the same group.
In trusted-local/full-scope mode, existing locations and existing active subjects are
usable; readable inactive subjects remain valid historical evidence. A future broader
resolver requires an explicit owning-family contract and registry update, not a permissive
fallback. Thus the reference-rich flight proof is initially trusted-local; protected
web use supports scalar facets and self-subject references, not implicit airport sharing.

Queries return only IDs/versions. Non-predicate nested references are neither returned
nor resolved by query; a subsequent show can fail independently. A reference predicate
is checked even when there are zero matches, preventing reference probing by counts.
All resolution shares the storage leaf's 100-resource budget. Authorization is evaluated
in one read snapshot and rechecked before response release or write commit, including
timed grants and identity eligibility. Loss denies the entire result/transaction.

Adapter precedence is shape/bounds, identity and registered operation admission, then
Section 6.2's authorized replay branch or Section 6.1's fresh target/nested authority.
Fresh write authority is not a prerequisite to returning a currently readable receipt.
For web, missing/hidden root or nested reference is resource_unavailable (404), missing
operation mapping is operation_unavailable (404), lost admitted access is access_changed
(409), invalid selection is identity_unavailable (403), capacity is capacity_exceeded
(429), unavailable preflight/key is admission_unavailable (503). Authorized malformed
cursors are invalid_request (400); authorized domain stale_cursor is access_changed (409).
Authorized domain validation (exit 2) maps to domain_failure (422), stale_version and
semantic/binding/archetype conflicts (exits 5/6) to domain_conflict (409); environment
or invariant/runtime failures map to admission_unavailable (503). Existence/reference
failures are resource_unavailable (404), without domain details. No reference IDs/values
are echoed. Trusted-local failures use the registry's CLI error codes;
bounded-capacity or missing configured cursor context is environment_failure, exit 7.

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

### 6.2 Closed write-replay authority

All six writes use the following matrix for every successful original receipt:
create has only a changed branch; the other five have changed and no-op branches.
It implements the current-read replay rule in permission-enforcement-and-web-admission.md,
not a second permission model. Resolver labels are mirrored in the integration companion.
`receipt.schema.catalog_read` resolves the root owning the exact returned revision/root
ID; `receipt.archetype.catalog_read` resolves the returned archetype. Binding IDs and
audit/receipt/version evidence inherit the indicated resource's disclosure authority.

| Command | Current receipt disclosure authority | Nested checks |
| --- | --- | --- |
| `facet_schema.create` | `receipt.schema.catalog_read` on the created root | None; no renewed owner catalog-admin check |
| `facet_schema.publish` | `receipt.schema.catalog_read` | None; no catalog-admin/use or active-revision check |
| `facet_schema.retire` | `receipt.schema.catalog_read` | None; retirement does not itself revoke read access |
| `item_archetype.facet_binding.set` | `receipt.archetype.catalog_read` | `receipt.schema.catalog_read` for the returned pinned schema revision; do not follow its current replacement binding |
| `item_archetype.facet_binding.remove` | `receipt.archetype.catalog_read` | None; the receipt returns binding evidence, not a schema revision/definition |
| `item.facets.update` | `receipt.item.read_current_authority` on the returned item | None; the receipt returns item/version/change evidence, not facet values, definitions or nested reference IDs |

For every row, permission-enforced replay requires the same initiating **account and
subject** as the stored attribution and a currently eligible identity/registered operation.
A changed session alone is allowed; a changed account-subject mapping is not. The adapter
may privately look up the receipt and its attribution after shape/admission checks solely
to select this branch. It MUST NOT disclose receipt existence, payload, semantic hash or
result before checking initiating identity and all matrix authorities. A foreign or local
receipt without protected attribution yields `command_id_unavailable` on the trusted-web
adapter (the deferred protected adapter retains `request_id_unavailable`). Missing/hidden
matrix resources yield `resource_unavailable` (404); authority lost between initial
authorization and release yields `access_changed` (409), with no receipt/result.

Only after those checks compare normalized command/envelope semantics: incompatibility
is `semantic_conflict`; compatibility returns Section 10.2's replay projection before
fresh version/epoch checks. A missing receipt takes the fresh Section 6.1 path and its
write checks. Recheck current disclosure at release; no replay branch writes anything.
Do not re-run fresh write/admin/use rights, status, item-type, binding eligibility or
reference validation on compatible replay. In particular neither original request
references nor the item's current or historical facet snapshot are dereferenced for an
item-update receipt. A separate `item.facets.show` still enforces all readback checks.
Catalog retirement, later binding removal and loss of edit/admin rights cannot alone
invalidate a receipt replay when the matrix's current read rights remain.

Trusted-local retains full scope and existing normalized-request/actor compatibility;
it does not fabricate a web identity or impose a new OS-identity ownership rule on local
receipts. This exception is not available to a permission-enforced adapter.

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
facts invalidate the cursor; never silently skip or duplicate matches. Section 11
defines the cursor wire contract; executable index/query-plan proof remains required.

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

The logical/storage design and the machine companions now define request/response
shapes, identity/type vectors, resolver mappings, cursor semantics, work continuity and
the migration/index plan. Review the new integration amendment before implementation;
then codify executable DDL/manifests/migration fixtures and runtime acceptance tests.
No promised runtime family is advertised before those tests pass. Do not widen this
slice to workflow recipes, live enrichment or a new reference-sharing model.

The structural schemas, fixture manifest and pure normalization/identity vectors are
now present (Section 10). Sections 5, 6 and 11 and the integration companion specify
the previously open work, resolver and cursor decisions. They do not satisfy persisted-state, permission, cursor,
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
   unknown fields and missing required fields have deterministic outcomes. A legal
   archetype/schema intersection does not authorize an incompatible concrete item type;
   same-value sets revalidate, whereas remove/copy-forward/replay do not reauthor values.
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
   cannot read unrelated items; current permissions govern historical readback. Each
   write's changed/no-op replay branches follow Section 6.2, including revoked read
   authority, retained read with lost write rights, and foreign initiating identities.
7. Scheduling: facet edit preserves time/policy meaning; queued, leased and attempted
   work outcomes follow the explicit freshness rule; no extra send occurs.
8. Queries: indexed equality, pagination invalidation, access revocation and capacity
   limits behave identically at small and large unrelated-ledger sizes; no JSON scan.
   First-page source races fail without retry/result/cursor; continuation races are
   stale_cursor, with current-authority and capacity precedence as in Section 11.3.
9. Concurrent writers: facet versus schedule edit has one winner and a stale conflict,
   not lost fields, half-updated indexes or premature nested transaction commits.
10. Flight proof: register, bind, attach, inspect, query and replace through commands;
    location/time authority and existing notification behavior remain unchanged.

The operator confirmed the initial scope on 2026-09-24: scalar-only fields, same-owner
archetype/schema bindings, optional facets, item/series-level values rather than
per-occurrence values, and two-command initial authoring. These product choices are
settled for the initial slice. Separately, the operator ratified the physical storage
design in [archetype-facet-storage.md](archetype-facet-storage.md) as v1.0 on 2026-09-25.
Neither acceptance closes the remaining engineering gates or advertises implemented
capabilities.

## 10. Machine-contract codification (draft)

The repository-only proposed registry is
`contracts/archetype-facet-contract-registry.v1.json`. It maps all eleven commands to
their exact request/response schema fragments and family versions. It is not imported
by runtime preflight, CLI dispatch, package capability declarations or the web allowlist.
The six `contracts/schemas/archetype-facet-*.schema.json` files define types, requests,
successes, handler failures, the fixture manifest and cursor payload. The integration
companion is `contracts/archetype-facet-integration.v1.json`. The fixture manifest is
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

All six writes support compatible replay. `facet_schema.create` replays only its
changed receipt; create collisions remain conflicts and there is no create no-op
receipt. Publish, retire, binding set, binding remove and item facet update may replay
their changed or no-op receipts. Prior/resulting version and binding facts stay exactly
as recorded, even if the target has since advanced; replay is not a current-state read.
For `item.facets.update`, replay returns
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
work and uses false. Section 5 defines verified retention and the exact true/false rule;
the boolean is not evidence of delivery or a count of cancelled/created work.

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
the facet handler schema does not replace or freeze them. Section 6.1 defines resolver
mappings, admission ordering and capacity wrappers. Fixture error
messages are illustrative safe prose, not byte-exact public message constants.

### 10.3 Pagination and validation limits

Catalog list defaults status=active and limit=25; explicit status selects active or
retired. Binding list returns only active bindings. Query returns current matching
item IDs/versions. All pages include the accepted decimal-string limit, `has_more`
and `next_cursor`; has_more=false requires null, true requires a nonempty opaque
cursor at most 4096 characters. Returned collection length cannot exceed limit.
Root IDs, facet keys and item IDs respectively determine the existing total order.

Section 11 and its machine companion specify token encoding, authenticated binding,
snapshot identity, expiry and access context. No fixture with an arbitrary token proves pagination
security or freshness. Likewise, JSON Schema checks structure, not NFC, declared-field
validation, hash correctness, foreign-key visibility, byte ceilings or transactional
invariants. Test-only pure oracles cover selected semantic vectors; no application
validator, database migration, index or command handler is introduced by this bundle.

## 11. Authenticated facet pagination v1

`contracts/archetype-facet-integration.v1.json` and
`contracts/schemas/archetype-facet-cursor.schema.json` define the dedicated
`spine.facet-cursor.v1` continuation. It does not extend or replace either existing
trusted-web cursor family. The three paginated commands are facet_schema.list,
item_archetype.facet_binding.list and item.facets.query. Show is never paginated.

### 11.1 Bytes, key and context

Token: `fc1.<base64url(payload)>.<base64url(mac)>`, unpadded canonical base64url,
at most 4096 ASCII bytes. Payload is closed canonical Spine JSON UTF-8 per the cursor
schema. MAC is HMAC-SHA256 with the preimage `ASCII("spine.facet-cursor.v1")`, one NUL
byte, then the exact payload bytes. Reject wrong version, padding, noncanonical
base64url, duplicate JSON keys, unknown fields, noncanonical JSON, invalid schema or
MAC with invalid_request/field=cursor. Verify MAC with constant-time comparison before
interpreting payload fields. Never log token contents or signature diagnostics.

Use a separately provisioned deployment secret of at least 32 random bytes per ledger,
not a model/request supplied key or the public vector key. Reads never create a key,
receipt or cursor cache. Trusted-local CLI receives key and context through protected
operator configuration; web receives them through service configuration. Missing config
fails preflight for paginated commands, including first pages, rather than issuing unsigned
cursors. This is configuration, not executor authentication. Provision a persistent random
`cursor_ledger_id` and `cursor_generation` with the key outside the ledger; use distinct
values for copies/clones and rotate generation after restore. These config IDs are not
canonical coordination IDs. Rotation invalidates outstanding cursors. No new DB columns.

`context_hash` is a keyed digest of the closed object containing `mode`,
`cursor_ledger_id`, `cursor_generation`, and `principal`. For trusted_local, principal
is `{os_uid: <canonical decimal string>}`; full-scope local users still do not assert a
web account. For permission_enforced, principal is the exact identity mapping from
`contracts/trusted-web-read-cursor.v2.json` (ledger/realm/recovery, account/subject/
binding revisions, selection ID and access_epoch). Full-scope single-operator web
remains permission_enforced for identity binding; its access proof records that
deployment mode. No caller-controlled actor field substitutes for this context.

For all three digest fields below, use lowercase hex HMAC-SHA256 over canonical JSON
of `{contract_version: <domain>, value: <specified object>}` with the same key.
Domains are `spine.facet-cursor-context.v1`, `spine.facet-cursor-access.v1`, and
`spine.facet-cursor-source.v1`; signatures retain their separate domain above.
Keying prevents a cursor digest becoming an oracle for low-entropy protected facts.

### 11.2 Query, source and access binding

`query_hash` is ordinary lowercase SHA-256 over canonical JSON of
`{contract_version:"spine.facet-query.v1", command:<canonical command>, request:<normalized request>}`.
The request excludes only cursor, includes contract_version and limit (default 25),
and fills list status=active. NFC/type normalization follows the pinned schema;
owner discriminators and exact schema/archetype IDs are retained. Changing limit,
predicate, owner, revision, status or command mid-pagination is invalid_request.
Bind this digest and command in every payload. Do not accept a token from another route.

Recompute the complete bounded authorized candidate set on each page in one snapshot,
not only the page after last_key. Use indexed enumeration plus LIMIT 101; more than 100
candidates or resolved resources fails capacity before returning any page. This is a
v1 total-candidate ceiling, not just a page limit. Do not silently cap or paginate an
incomplete set. Candidate enumeration includes nonmatching items/roots, so a later
matching value or newly visible candidate changes the snapshot. No global JSON scan.

`source_snapshot_hash` covers a closed `{command, query_hash, facts}` object, with
facts exactly as follows, ordered by the specified primary key:

- Schema list: facts is `{roots: [...]}` containing all authorized roots in the named owner (before status filter), each
  `{facet_schema_id, current_revision_id, status}`; immutable revision IDs suffice to
  bind returned definition bytes. No hidden roots or hidden-root counts.
- Binding list: facts is `{archetype, bindings}`; archetype is
  `{item_archetype_id, current_revision_id, status}`. Each bindings element is
  `{binding, schema}` in facet_key order, where binding uses the types schema's exact
  `$defs/binding` representation and schema is its root's
  `{facet_schema_id, current_revision_id, status}`. A missing
  nested read permission denies the page, rather than hashing hidden schema facts.
- Item query: facts is `{schema, candidates, reference}`. Schema contains exactly
  `facet_schema_id`, `current_revision_id`, `status`, `facet_schema_revision_id` and
  `definition_hash` for the selected root/exact revision. Candidates are authorized
  candidates `{item_id, current_version, owner, owner_revision}` ordered by item ID,
  and reference is null or, for a reference predicate, its authorized
  `{target_kind, target_id, status}`.
  Query typed-index parity with current_version is mandatory; mismatch fails environment,
  not an empty result. Non-predicate referenced subjects/locations are not dereferenced.

These canonical objects use public wire field spellings and decimal-string versions.
Immutable revision guarantees and all-version transactional indexes make item-version
facts sufficient without decoding every candidate's JSON. Do not hash full DB/WAL files.

`access_hash` binds `{mode, identity, memberships, grants, deployment_access_mode}`.
For trusted_local, identity equals the local principal and memberships/grants are empty;
deployment_access_mode is trusted_local. Otherwise identity is `{principal, rows}`:
principal is the web principal; rows contains the ledger_access_state, web_operators,
login_accounts, account_subject_bindings and selected subjects rows used by admission.
Memberships contains all subject_memberships rows for the selected subject, with the
referenced subject_groups and adopted_access_groups rows. Grants contains access_grants
whose grantee is that subject or one of those groups and resource is in the named scope
or explicit roots, plus their current-revision access_grant_operations rows. Select these
before time/status filtering; include future starts and ended/revoked rows. Each proof
row is `{table, key, row}`; key is its ordered SQL primary-key value array; row includes
all columns from the schema-matched runtime, with integer columns and integer key values
converted to canonical decimal strings and SQL NULL to JSON null. Sort by table then
canonical key bytes (BINARY), deduplicate equal table/key pairs. Missing required admission
rows fail admission, not a hash of absence. deployment_access_mode is the server's
multi_user or single_operator_full_scope configuration. The shared 100-row proof limit
includes all three arrays. No incomplete proof can authorize continuation. These private facts are
only keyed-hashed, never returned. Re-evaluate permissions at current server time on
each page, and recheck time/authority at release. Future starts/ends of relevant grants
or memberships bound `authorization_valid_until_utc` to the earliest transition strictly
after first-page evaluation (null if none); child pages preserve it. No sliding renewal.

### 11.3 Continuation and errors

Order is BINARY root ID, facet_key or item ID respectively. last_key is exactly the last
returned key, never a row offset. has_more is true iff the complete authorized matching
set contains a later key; only then mint next_cursor. Empty/terminal pages return null.
Children preserve context/query/access/source hashes and original issued/expires/deadline,
changing only last_key. Replaying a cursor against unchanged facts returns the same
logical page; no durable read evidence is created. Concurrent source changes between
snapshot evaluation and release cause revalidation failure, never a mixed page.

Perform exactly one snapshot construction per request, with no automatic reconstruction
retry or budget reset. Revalidate current identity/authority, then the complete source
proof before release, within the same operation budget. If only source facts changed:
a first page (no cursor) returns CLI `environment_failure`, exit 7, or web
`access_changed`, HTTP 409 (`first_page_source_changed` in the companion); a continuation
returns `stale_cursor`, mapped to web `access_changed`, HTTP 409. Neither returns a
result, count or cursor, nor creates durable evidence. The caller may issue a new
first-page request. Current identity/hidden-resource/lost-access errors take precedence
over source comparison; if completing revalidation would exceed a deadline or resource
budget, return capacity rather than guessing whether the source changed.

Service time, not action_timestamp_utc, governs `issued_at <= now < expires_at` with
`expires_at = issued_at + 900 seconds`; now must also precede the non-null authorization
deadline. A non-null deadline must be later than issued_at; crossing a relevant access
transition before first-page release fails `access_changed` on web (CLI environment_failure,
exit 7), with no token and no internal retry. A continuation crossing its bound deadline
is stale_cursor, subject to current identity/hidden-resource errors first. Malformed dates/future-issued payload
or mismatched query/command is invalid_request.
Authentic but expired, changed context/access/source or missing last_key is stale_cursor.
Web maps stale_cursor to access_changed; invalid selection/hidden targets take the
Section 6.1 errors before cursor comparison. Key rotation yields invalid_request because
the old signature no longer verifies. Restart with unchanged protected config preserves
continuation; there is no retained volatile proof dependency. Full proofs are bounded
and freshly recomputed. SQL/deadline/byte/proof overflow returns capacity, not stale or
false completeness. These rules cover local and future web transport without enabling
a web route. Pure cryptographic/decision vectors are not runtime pagination proof.
