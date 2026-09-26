# Spine Archetype Facet Storage

Status: Accepted v1.0 — physical design ratified; not implemented
Date: 2026-09-24
Ratified: 2026-09-25
Scope: SQLite persistence, migration, typed query indexes and storage proof for facets

## 1. Authority and boundaries

[Archetype facets](archetype-facets.md) owns logical semantics, limits, identities,
commands and readback. [Decision 0004](decisions/0004-versioned-item-facets.md) owns
the accepted versioned architecture; this leaf owns its physical layout. The Spine-wide persistence
owner is [STORAGE_ATOMICITY_SPEC.md](STORAGE_ATOMICITY_SPEC.md). This leaf is the
authoritative accepted facet SQL layout, ratified by the operator on 2026-09-25. It
does not ratify unsettled logical choices or introduce a second item, audit,
permission or work model.

The existing [machine registry](../contracts/archetype-facet-contract-registry.v1.json),
[type schema](../contracts/schemas/archetype-facet-types.schema.json) and
[fixture manifest](../contracts/archetype-facet-fixture-manifest.json) remain unchanged.
Storage columns are not new public response fields. No migration number, implemented
family, pack capability, CLI command or web route is activated by this specification.

## 2. Layout assessment and selection

| Layout | Benefit | Cost against the ratified model | Choice |
| --- | --- | --- | --- |
| Domain relational tables (flight, lesson, etc.) | Direct SQL typing and familiar joins | Every operator-defined schema becomes a DDL deployment; domain taxonomy enters core | Reject |
| Canonical JSON only | Exact portable definitions, compact version snapshots | Field filtering needs JSON scans or dynamic indexes; embedded IDs have no FK protection | Reject as the whole layout |
| EAV as canonical values | Dynamic fields with typed rows and indexes | Reconstructing a complete version requires many rows; absence, full replacement and canonical bytes become harder to prove | Reject as canonical authority |
| Hybrid: relational identity/history plus canonical JSON and derived typed rows | Stable schema, exact historical decoding, relational references, bounded equality lookup | Must maintain and verify projection parity atomically | Select |

Definitions and value objects are canonical JSON, not arbitrary JSON bags. Relational
rows pin exact definitions, bindings, item versions and authoring receipts. Only current
queryable values have scalar search rows. All present references, including non-queryable
historical references, have relational reference rows. No dynamic DDL per schema, JSON
expression index per field, FTS, arbitrary JSON path or EAV reconstruction on readback.

## 3. SQL notation and canonical representation

The inventories below specify every column. `T` means SQLite TEXT with BINARY collation;
`I` means SQLite INTEGER with `typeof(column)='integer'`; `?` permits SQL NULL. Other
columns are NOT NULL, including TEXT primary keys. IDs are nonempty and retain their
existing wire domains. Versions/counts are integers in storage and canonical decimal
strings on the wire. Positive versions are 1 through 9223372036854775807; overflow
fails without wraparound. Booleans in derived columns are integer 0/1. No REAL columns.
SQL NULL is never an authored facet value.

For nullable integer columns, the typeof constraint applies only to non-null values.
An FK table name without an explicit column list below means that table's single-column
primary key; all multi-column FKs are written explicitly. Initial decoder-selector
values are the only accepted values in this storage version; expanding them requires
an explicit compatible decoder/schema change, not permissive input acceptance.

All FKs below use `ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED`.
There is no cascade delete. PK/UNIQUE keys use exact BINARY equality. A composite FK's
parent key must have the explicitly listed PK or UNIQUE constraint, not merely a
prefix of another index. Constraints that inspect another table use triggers or
mutation-scoped verification as assigned in Section 5, not illegal cross-table CHECKs.

`definition_json` is precisely the normalized `definition` object from logical
Sections 3 and 10.1, encoded with `spine.canonical-json.v1`. It contains display_name,
description, compatible_item_types and fields; it does not contain root identity or
the revision envelope. `definition_hash` is the existing SHA-256 of the canonical
`spine.facet-definition.v1` preimage, not a hash of raw input or a SQLite JSON serializer.
`values_json` is the canonical values object, not the entry envelope. Empty `{}` is
legal only where the pinned definition allows it. An absent entry has no entry row.

Writers normalize once using the logical rules and persist those exact UTF-8 bytes as
TEXT. Reject duplicate JSON object keys during input parsing, unpaired surrogates,
undeclared fields and invalid types before serialization. SQLite `json_valid` alone
does not prove any of these properties. Readers use a versioned decoder and verify
the pinned definition/hash, not the latest catalog revision. Never silently normalize
stored noncanonical bytes during readback. Store `canonical_json_version` and
`definition_contract_version` per definition, and `value_contract_version` per entry;
these are immutable decoder selectors, not additions to the existing hash preimage.
Unknown selectors fail closed. A future upgrade must retain old decoders or provide
an explicit semantics-preserving migration; it cannot reinterpret history in place.

## 4. Table inventory

### 4.1 `facet_schemas` — root lifecycle

| Column | Type | Constraint/meaning |
| --- | --- | --- |
| facet_schema_id | T | PK; logical command-derived ID |
| owner_kind | T | system, subject, subject_group |
| owner_subject_id | T? | FK subjects(subject_id) |
| owner_group_id | T? | FK subject_groups(group_id) |
| schema_key | T | Logical ASCII key domain |
| status | T | active or retired |
| current_revision_id | T | Composite FK with facet_schema_id to revisions below |
| created_command_receipt_id | T | FK command_receipts(command_receipt_id) |
| retired_command_receipt_id | T? | FK command_receipts(command_receipt_id) |

Owner CHECK: system has neither ID, subject has only subject ID, subject_group has only
group ID. Active requires null retired receipt; retired requires a receipt. Root identity,
owner, key and creation receipt are immutable. Retirement is terminal. Actor/time/command
evidence comes from referenced common receipts, not a parallel actor/time ledger.

Three UNIQUE partial indexes enforce owner-local keys, **including retired roots**:
`facet_schemas_system_key_uq(schema_key) WHERE owner_kind='system'`;
`facet_schemas_subject_key_uq(owner_subject_id,schema_key) WHERE owner_kind='subject'`;
`facet_schemas_group_key_uq(owner_group_id,schema_key) WHERE owner_kind='subject_group'`.
A UNIQUE on nullable owner columns alone is insufficient and MUST NOT substitute.

### 4.2 `facet_schema_revisions` — immutable definitions

| Column | Type | Constraint/meaning |
| --- | --- | --- |
| facet_schema_revision_id | T | PK; logical command-derived ID |
| facet_schema_id | T | FK facet_schemas(facet_schema_id) |
| revision_number | I | Positive; first=1, subsequent=previous+1 |
| definition_contract_version | T | Initially spine.facet-schemas.v1 |
| canonical_json_version | T | Initially spine.canonical-json.v1 |
| definition_json | T | Canonical object, UTF-8 bytes <=32768 |
| definition_hash | T | Exactly 64 lowercase hexadecimal characters |
| created_command_receipt_id | T | FK command_receipts(command_receipt_id) |

UNIQUE `(facet_schema_id,revision_number)` and
`(facet_schema_id,facet_schema_revision_id)`. The root's composite FK targets the latter,
so a pointer cannot refer to another root. Root and first revision insert in one
transaction using deferred FKs. No uniqueness on definition_hash: distinct roots or
later revisions may legitimately have identical portable definitions. Publishing
against an unchanged current definition remains the logical no-op.

### 4.3 `facet_schema_fields` — immutable definition projection

| Column | Type | Constraint/meaning |
| --- | --- | --- |
| facet_schema_revision_id | T | FK facet_schema_revisions |
| field_key | T | Logical key domain |
| value_type | T | text, enum, boolean, integer, date, reference |
| required | I | 0 or 1 |
| queryable | I | 0 or 1 |
| target_kind | T | subject/location only for reference; otherwise literal none |

PK `(facet_schema_revision_id,field_key)`; UNIQUE
`(facet_schema_revision_id,field_key,value_type,queryable)` and
`(facet_schema_revision_id,field_key,value_type,target_kind)` support child FKs.
Exactly one row per declaration (1–32), with exact parity to definition_json. Limits,
enum choices and display metadata remain in the canonical definition; no competing
relational copies. Derived field rows are generated at publication, never changed
when a binding moves to a newer revision.

### 4.4 `archetype_facet_bindings` — explicit binding history

| Column | Type | Constraint/meaning |
| --- | --- | --- |
| facet_binding_id | T | PK; logical command-derived ID |
| item_archetype_id | T | FK item_archetypes(item_archetype_id) |
| facet_key | T | Logical key domain |
| facet_schema_revision_id | T | FK facet_schema_revisions |
| status | T | active, superseded, retired |
| created_command_receipt_id | T | FK command_receipts |
| ended_command_receipt_id | T? | FK command_receipts |

UNIQUE `(facet_binding_id,item_archetype_id,facet_key,facet_schema_revision_id)`.
`archetype_facet_bindings_active_uq(item_archetype_id,facet_key) WHERE status='active'`
enforces one active binding. Active has null ended receipt; others require it.
Only active->superseded or active->retired transitions are legal. Identity, target,
key and creation evidence are immutable. Replacement ends the old binding before
inserting the new one within the same transaction; remove changes the existing row
to retired. No replacement/tombstone ID is generated by remove.

### 4.5 `item_facet_snapshots` — complete-version marker

| Column | Type | Constraint/meaning |
| --- | --- | --- |
| item_id | T | Part of PK |
| item_version | I | Positive; part of PK |
| entry_count | I | 0–8 |
| values_bytes | I | 2–65536; canonical map of facet_key -> values object |

PK/FK `(item_id,item_version)` -> coordination_item_versions(item_id,version).
One marker per item version, including versions with no facets and non-event/task
versions (always empty). The empty snapshot has count=0, bytes=2 for `{}`.
The counts are checked projections, not an independent source of truth. A missing
marker after migration is an invariant failure, not implicit empty data. This makes
copy-forward omission observable even for removal of the last entry.

### 4.6 `item_facet_entries` — immutable values and authoring evidence

| Column | Type | Constraint/meaning |
| --- | --- | --- |
| item_id | T | Part of PK |
| item_version | I | Positive; part of PK |
| facet_key | T | Logical key; part of PK |
| facet_schema_revision_id | T | FK facet_schema_revisions |
| facet_binding_id | T | Binding FK below |
| item_archetype_id | T | FK item_archetypes |
| item_archetype_revision_id | T | Archetype revision FK below |
| archetype_selection_source | T | operator_explicit, agent_selected, imported |
| archetype_source_ref | T? | Null means absent public source_ref; otherwise nonempty |
| value_contract_version | T | Initially spine.item-facets.v1 |
| values_json | T | Canonical object, UTF-8 bytes <=16384 |
| source_command_receipt_id | T | FK command_receipts; original authoring, not copy-forward |

PK `(item_id,item_version,facet_key)`; FK pair to item_facet_snapshots;
UNIQUE `(item_id,item_version,facet_key,facet_schema_revision_id)` for projections.
Composite FK `(facet_binding_id,item_archetype_id,facet_key,facet_schema_revision_id)`
to binding UNIQUE above prevents cross-binding substitution. Composite archetype FK
`(item_archetype_id,item_archetype_revision_id)` requires adding the corresponding
UNIQUE index `item_archetype_revisions_root_revision_uq` to existing
item_archetype_revisions during migration. Existing global
revision PK already implies uniqueness; the new index makes that parent key explicit.

Entry archetype evidence is pinned at authoring, not a FK to a newly generated
copy-forward assignment ID. On `set`, compare it with the canonical current assignment;
on retention, preserve it byte-for-byte even if catalog metadata has advanced. Do not
introduce a generated value, snapshot or authoring identity absent from logical Section 3.1.

### 4.7 `item_facet_references` — FK protection for every historical reference

| Column | Type | Constraint/meaning |
| --- | --- | --- |
| item_id | T | Part of PK |
| item_version | I | Part of PK |
| facet_key | T | Part of PK |
| field_key | T | Part of PK |
| facet_schema_revision_id | T | Entry/field FKs below |
| value_type | T | Constant reference |
| target_kind | T | subject or location |
| subject_id | T? | FK subjects(subject_id) |
| location_id | T? | FK locations(location_id) |

PK `(item_id,item_version,facet_key,field_key)`. FK
`(item_id,item_version,facet_key,facet_schema_revision_id)` to entries; FK
`(facet_schema_revision_id,field_key,value_type,target_kind)` to fields. Exactly the
target-kind-specific ID is non-null; its string equals the canonical value for field_key.
Exactly one row exists per present reference field, even if queryable=false. No row for
an absent optional reference. Existence is FK-enforced; current activity/visibility is
not encoded as a stale boolean in this table. Historical rows prevent hard deletion of
referenced subjects/locations but do not prevent allowed lifecycle changes.

### 4.8 `item_facet_current_values` — replaceable typed query projection

| Column | Type | Constraint/meaning |
| --- | --- | --- |
| item_id | T | Part of PK; FK coordination_items(item_id) |
| facet_key | T | Part of PK |
| field_key | T | Part of PK |
| item_version | I | Current version at transaction commit |
| facet_schema_revision_id | T | Entry/field FKs below |
| value_type | T | Same six types as declaration |
| queryable | I | Constant 1 |
| value_text | T? | text/enum/date/reference only |
| value_integer | I? | integer/boolean only |

PK `(item_id,facet_key,field_key)`. Entry FK uses
`(item_id,item_version,facet_key,facet_schema_revision_id)`; declaration FK uses
`(facet_schema_revision_id,field_key,value_type,queryable)`. CHECK enforces exactly
one typed value column non-null and boolean integer in (0,1). Date is validated ISO
text; integers use lossless signed-64-bit conversion, never float; enum/text are NFC
BINARY strings. Reference uses its literal ID in value_text; the exact revision/field
determines target kind, and the matching historical reference row is required.

One row per present queryable field in the current snapshot, none for other fields
or historical versions. At most 256 rows per item. Item ownership, membership, target
visibility and lifecycle are deliberately not copied here. Join their live authoritative
records; an access-owner transfer does not require rewriting facet history or search
values. This table cannot reconstruct a complete snapshot and MUST NOT be used to do so.

## 5. Enforcement and object manifest

SQL CHECKs enforce local domains, nullability, byte bounds (`length(CAST(x AS BLOB))`),
owner alternatives and typed value alternatives. Use `json_valid` and `json_type='object'`
for JSON shape as additional checks, not as a replacement for the canonical validator.
FKs enforce existence and the specified composite relationships. Partial UNIQUE indexes
enforce active bindings and owner-local keys. Never use INSERT OR REPLACE to bypass
uniqueness, receipt collision, immutability or stale expectations.

Required trigger names/roles for the implementation manifest:

- `<table>_immutable_update` and `<table>_immutable_delete` for
  facet_schema_revisions, facet_schema_fields, item_facet_snapshots, item_facet_entries,
  item_facet_references: unconditional ABORT for ordinary UPDATE/DELETE.
- `facet_schemas_identity_update`, `facet_schemas_terminal_update`,
  `facet_schemas_no_delete`: immutable columns, no revival or revision-pointer change
  after retirement, and no ordinary DELETE.
- `archetype_facet_bindings_identity_update`, `archetype_facet_bindings_terminal_update`,
  `archetype_facet_bindings_no_delete`: immutable columns, only the two legal terminal
  transitions, and no ordinary DELETE.
- `facet_schema_revisions_contiguous_insert`: new number is max(root)+1, using the
  root/revision UNIQUE index, not a global revision scan.

Mutation-scoped validation under the outer transaction enforces normalized bytes/hash,
complete field/reference projections, schema compatibility, same-owner binding, active
target eligibility for fresh sets, original receipt attribution, complete marker counts,
and equality of current index rows to the new snapshot. It also checks the root pointer
selects its latest revision and that each item's current indexed version matches its
shell. These are multi-row invariants; SQLite has no general deferred commit trigger.
They must run on every relevant writer before commit, with FK checking still on.
Do not claim triggers alone make raw SQL authoring safe.

Schema manifests must enumerate the concrete expansion of these trigger names, tables,
PK/UNIQUE structures, and Section 9 indexes using the existing type/name/DDL-fingerprint
contract. This document is not the executable manifest. Tests must reject definition
drift as well as missing names. Explicit deep verification recomputes all projections;
routine preflight checks schema objects only, and ordinary commands check touched roots
or versions only. Failure is fail-closed; reads never fix rows or write diagnostics
into the command ledger merely because an invariant failed.

## 6. Versioning, transactions and evidence

For a fresh changed item update, in the existing outer write transaction:

1. Apply logical validation precedence and replay checks. Recheck current item version,
   current authority, active binding expectations and referenced targets while locked.
2. Load the previous complete snapshot and the exact definitions required (at most
   eight). Compute the full replacement snapshot, retaining unchanged source evidence.
   Validate final count/byte limits before inserting any version.
3. Allocate the next canonical item version and copy all existing supporting facts
   through the common item-version path. Facets are a required supporting set on
   **every** version producer, including schedule, lifecycle, recurrence, reminder,
   binding reconciliation and profile-application paths, not just item.facets.update.
4. Insert marker, entries and all reference rows. Copied entries preserve schema/binding,
   archetype evidence, decoder version, values_json and source receipt; only the composite
   item-version key changes. Changed set entries use this command's receipt ID.
5. Replace this item's current typed rows from the complete new snapshot, update the
   shell version, perform any required existing work reconciliation, and validate
   touched invariants. Other items' projections and historical rows remain unchanged.
6. Persist one changed-write audit and one common receipt, then commit all changes.
   Deferred receipt FKs permit entries before receipt insertion. No helper commits.

Unrelated item edits copy facets without requalifying retained catalog status or current
reference access. This does not grant disclosure of an unreadable reference. A fresh
same-value set still performs the logical catalog/reference checks before deciding no-op.
Archetype change/clear with retained entries fails, not silent clearing. Final removal
creates an empty marker and deletes only that item's current derived rows.

Fresh no-op: receipt only, no item version, audit, marker, projection churn or reconciliation.
Compatible replay: return recorded identities with logical response substitutions, zero
new rows. Conflicting replay, validation failure, lock timeout, disk full, interrupted
statement or deferred-FK failure: roll back all tentative facts. After an uncertain client
response, retry the same command_id; do not generate a new one. Use existing semantic
facts/hashes and command-derived IDs; no storage-specific idempotency table.

Item facet changes use existing audit_log with the logical audit_id. Catalog/binding
changes use existing coordination_catalog_audit_log with that audit_id stored as
catalog_audit_id; the migration extends its closed resource_kind CHECK with
`facet_schema` and `archetype_facet_binding`. Use the canonical command as action,
the terminal effect as reason_code, and common actor/command/time evidence. Receipt
result facts store exactly the owning command's stable outcome fields; audit payload
hashing follows the existing audit writer. No second facet audit table. SQL layout must
not change logical replay response transformations or duplicate a composite audit.

Facet-only version changes follow logical Section 5's verified-retention rule. Its
continuity check shares this transaction, leaves work/attempt rows unchanged and fails
atomically on unexpected semantic drift. Runtime proof remains required; this leaf
does not define a second notification reconciliation engine.

## 7. References, retirement and historical decoding

Fresh attachment/replacement validates existing active subjects or existing locations,
plus applicable current read authority. Locations have no active/inactive lifecycle
in this slice. The FK is necessary but insufficient. Do not create
targets implicitly, treat arbitrary strings as references, or grant access through
membership in a facet. Fresh binding requires active compatible catalogs with identical
owners. Retired roots keep revisions and bindings; retirement need not rewrite all
bindings or values. Fresh sets through a binding to a retired root are denied even if
that binding row is still active. Removing it remains allowed.

Readback fetches exact historical entries and definition versions under current item
authorization, then resolves every reference's current visibility/state. An unreadable
reference denies the entire facet readback with the existing safe error boundary;
there is no null redaction or leaked target ID. Readable inactive subjects remain in
history with inactive state. No current catalog-use permission is required solely to
decode an already published item snapshot. An unsupported decoder or missing canonical
row is an invariant/admission failure, not empty values.

Current `locations` has no status column. As confirmed on 2026-09-24, existence plus
applicable read permission qualifies a location reference. Readback represents an
existing readable location as status=active for the reference envelope; that is not
a location lifecycle fact. Storage adds no status flag or retirement behavior.

No hard-delete/retention command is introduced. Retirement is not erasure. Referenced
definitions, bindings, receipts, archetype revisions and reference targets remain
protected by FKs; triggers additionally protect unreferenced facet history in this
slice. Canonical-data erasure or compaction needs a separate accepted policy. Only the
current typed projection is disposable/rebuildable, in an explicit maintenance
transaction with commands stopped and parity checked before release. Definition-field
or historical-reference projection repair requires a reviewed maintenance procedure
that restores immutability triggers; it is never an ordinary reader's action.

## 8. Migration and rollback

The inspected baseline is ledger schema 15. Assign the next available schema number
only at implementation; rebase on intervening migrations rather than reserve 16 now.

1. Stop all ledger writers, including direct CLI and worker use. Take and verify a
   consistent SQLite backup, account for WAL state, and check migration-space needs
   for historical markers, indexes and any audit-table rebuild. Do not copy a live
   main file alone or delete sidecars as a migration shortcut.
2. Run explicit deep verification under the existing migration path. Admit only the
   expected predecessor schema. The facet migration creates the eight tables and
   listed constraints/indexes/triggers, adds the archetype composite parent index,
   and rebuilds the catalog audit CHECK if SQLite requires it. Preserve every existing
   audit row, key, index and trigger; compare pre/post evidence rather than recreate
   historical receipts.
3. Backfill one empty marker for **every existing coordination_item_versions row**,
   with entry_count=0 and values_bytes=2. No definitions, bindings, values, scalar
   rows, facet audit or command receipts are synthesized. No inference from old JSON,
   archetype names, provider metadata or pack content is permitted.
4. Verify marker/version cardinality and all historical empties, foreign keys, objects,
   and existing data preservation before activation. Advance the global schema version
   only with the successful migration transaction. If any stage fails, roll back;
   a partial backfill must not be accepted as a supported schema. If the migration
   tool commits a chain one migration at a time, the backup covers the entire chain;
   do not claim the chain itself was one atomic transaction.
5. Package the matching object manifest and update every item-version writer to create
   or copy facet markers, even when facet commands are not exposed. No mixed-version
   writer rollout: older runtimes must fail schema preflight. Verify contract/decoder
   availability before advertising facet command families.

Backfill is deliberately ledger-size-dependent **maintenance**, not startup or command
preflight. A large deployment may need a separately designed resumable migration; this
specification does not hide partial availability or reopen a general scalability project.

Rollback before migration commit uses transaction rollback. After commit, either use
a facet-aware runtime compatible with the new schema or stop all writers and restore
the verified pre-migration backup with the matching runtime. No automatic down-migration,
table dropping or binary downgrade onto the new file. Restoring the backup loses later
writes and requires explicit operator acceptance. Preserve ledger identity and existing
recovery/session invalidation rules from [ledger-instance-identity](ledger-instance-identity.md)
and the web admission contract; never manufacture a second identity for the restored file.

## 9. Index and query-plan contract

In addition to PK/UNIQUE indexes above, require these named indexes:

| Index | Columns / predicate | Purpose |
| --- | --- | --- |
| facet_schemas_owner_list_idx | owner_kind, owner_subject_id, owner_group_id, status, facet_schema_id | Explicit-owner keyset list, not schema_key ordering |
| archetype_facet_bindings_list_idx | item_archetype_id, status, facet_key | Active binding list |
| archetype_facet_bindings_revision_idx | facet_schema_revision_id, facet_binding_id | Reverse FK/maintenance lookup |
| item_facet_entries_revision_idx | facet_schema_revision_id, item_id, item_version, facet_key | Referenced definition checks/deep verification |
| item_facet_entries_binding_idx | facet_binding_id, item_id, item_version, facet_key | Binding FK maintenance |
| item_facet_entries_archetype_revision_idx | item_archetype_id, item_archetype_revision_id, item_id, item_version | Historical archetype FK maintenance |
| item_facet_references_subject_idx | subject_id, item_id, item_version WHERE subject_id IS NOT NULL | Subject FK protection |
| item_facet_references_location_idx | location_id, item_id, item_version WHERE location_id IS NOT NULL | Location FK protection |
| item_facet_current_text_idx | item_id, facet_schema_revision_id, field_key, value_type, value_text, facet_key WHERE value_text IS NOT NULL | Candidate-rooted typed equality |
| item_facet_current_integer_idx | item_id, facet_schema_revision_id, field_key, value_type, value_integer, facet_key WHERE value_integer IS NOT NULL | Candidate-rooted integer/boolean equality |

Add child-receipt lookup indexes named `<table>_<column>_idx` for every receipt FK
column in roots, revisions, bindings and entries. These are maintenance access paths,
not an invitation to delete receipts. Existing supporting permission/owner indexes
remain authoritative; do not duplicate owner state into facet indexes.

Exact-version item read uses snapshot PK -> entry PK prefix -> definition PK ->
reference PK prefix. Catalog read uses root/revision PKs; catalog/binding lists use
the owner/status or archetype/status indexes with keyset continuation. No historic
scan is needed for copy-forward: fetch only the current complete snapshot.

Equality query accepts only subject/subject_group item owners; reject system owner
before query execution. System-owned schema definitions remain supported and confer
no item access. Equality query is permission-first: resolve selected account, requested owner, exact
schema revision and field under logical Section 6.1; then enumerate bounded
authorized item candidates **in that owner scope**, ordered by item_id, using existing
owner/grant indexes. Direct CLI can omit web authorization but still uses the explicit
owner and operational bounds. Probe current typed rows for each admitted item using
the applicable item-leading typed index and its pinned current item_version. A
representative per-candidate probe is:

```sql
SELECT 1 FROM item_facet_current_values
WHERE item_id = :authorized_item_id AND item_version = :current_item_version
  AND facet_schema_revision_id = :revision AND field_key = :field
  AND value_type = :type AND value_text IS NOT NULL AND value_text = :value
LIMIT 1;
```

The integer form uses value_integer. Decode/normalize the query value against the
pinned definition before binding SQL parameters. Do not CAST stored strings during
predicate evaluation, use NOCASE, or equate boolean true with integer 1 across types.
Multiple matching facet keys yield one item/version result. Current means the shell's
version, not all history; it does not add an undocumented active-only item filter.
Publication/retirement of definitions never switches the queried revision.

Fetch enough authorized candidates to establish the page and permitted lookahead,
within the shared resolution budget. If that budget is exhausted before completeness
or has_more can be established, return capacity failure, not a truncated successful
page or an empty answer. Pagination and source invalidation MUST use logical Section
11's authenticated facet cursor contract, including its complete bounded candidate
snapshot; physical keyset SQL is not that contract.
Permission predicates apply before revealing match/existence counts. Reference equality
also requires logical Section 6.1's reference disclosure resolver; knowing an ID is not authority.

EXPLAIN QUERY PLAN fixtures must show indexed SEARCHes rooted in the selected item,
owner or archetype. Reject unrestricted scans of item_facet_entries, current_values,
coordination_item_versions or canonical JSON functions in public filter plans. A
bounded temporary sort/dedup over at most admitted candidates is acceptable; a global
sort is not. Plan assertions target these properties, not SQLite's unstable prose or
planner numeric IDs. Bind the candidate loop explicitly if the optimizer would invert
it; prove VM-step bounds with large unrelated-owner and historical datasets.

## 10. Capacity and cost model

Logical maxima remain: 32 fields/definition; 32768 definition bytes; eight entries per
snapshot; 16384 bytes per value object; 65536 bytes for the canonical map of all item
values; changes array at most eight; page limit 1–100/default 25; at most 100 resource
resolutions per request. Reference/schema/item checks share that budget, not separate
100-resource allowances. Large valid snapshots may therefore require the documented
capacity failure on permission-enforced readback; do not invent partial facet reads.

For this leaf, use the existing trusted web operational ceiling values as
the upper bounds for facet reads/writes, including trusted-local query commands:
1 MiB request, 4 MiB response, 5-second end-to-end deadline including at most 2-second
SQLite busy wait, and 100000 SQL VM steps. Lower configured limits are permitted.
Logical Section 6.1 maps capacity to the adapter's existing safe envelope;
this leaf does not invent a public error code or let helpers reset the shared budget.
Migration and explicit deep verification are separately admitted maintenance paths.

Per changed item version, new facet history is at most one marker, eight entries,
and 256 reference rows, plus the existing item-version support/audit/receipt facts.
Canonical values remain <=64 KiB, but total physical cost includes evidence, IDs,
definitions already stored separately, row headers and B-tree pages; it is **not** a
64 KiB disk bound. Current index replacement writes/deletes at most 256 rows each.
Per new definition: one revision and <=32 declaration rows. No historic scalar search
rows are copied. Schema publication/retirement does not visit every using item.

Immutable snapshot copying grows with successful item versions, including unrelated
edits. This is deliberate bounded-per-write growth, not bounded-total-disk storage.
No TTL, deletion policy, compression/dedup store, background rebuild, scanner, or idle
receipt is introduced. Existing storage safeguards remain; retention policy is deferred.
Unbounded ID/source-ref wire domains do not override the request/response byte ceiling.

## 11. Concurrency and failure behavior

Use the existing outer `BEGIN IMMEDIATE` command transaction, with bounded lock wait.
Compare expected current item/revision/binding again after acquiring it; two writers
from one version yield one committed winner and one stale/conflict result, never
silent field loss. Public subcommands are not an atomicity mechanism. Shared helpers
must participate in the one transaction, including notification reconciliation when
its remaining contract is settled.

Readers use one consistent read transaction for root, definition, snapshot, typed
index and source membership checks. They see the pre-commit or post-commit version,
not a mixture. HTTP release rechecks/cursor invalidation remain owned by permission
and facet cursor contracts. A typed index is not an authorization cache. Concurrent
subject inactivation versus attachment must serialize: attachment either sees active
and commits before retirement, or fails the fresh-target check; later history stays
readable subject to current permission. Catalog retirement versus set follows the
same ordering. A receipt retry after a lost response does not redo either mutation.

Inject failures before/after snapshot insert, projection replacement, audit/receipt
insert and at deferred-FK/commit. Verify old shell, all supporting sets, current indexes
and receipt inventory remain coherent. No external adapter runs inside this facet
authoring transaction; no newly queued work or send is justified solely by facet data.

## 12. Required executable fixtures (not yet provisioned)

These extend, not replace, the existing structural/pure-vector fixtures. The following
IDs name required future tests; a Markdown row is not runtime verification evidence.

| Family | Observable oracle |
| --- | --- |
| FS-01 representation | Existing normalization/hash vectors yield identical stored bytes; reordered equivalent input no-ops; malformed JSON, duplicate keys, surrogates and unknown decoder selectors fail safely |
| FS-02 relational identity | Cross-root revision pointer, cross-binding/revision entry, wrong reference kind, duplicate owner key (including system/retired), duplicate active binding and version gaps are rejected |
| FS-03 immutable decoding | Publish/retire/replace binding leaves old entry/definition bytes and hashes unchanged; old item decodes using pinned revision despite different current definition |
| FS-04 full snapshots | Unrelated item mutations copy all eight entries and original provenance; absent versus empty object differs; last removal yields explicit empty marker; omitted marker/projection parity fails |
| FS-05 typed queries | Flight number/location matches, NFC/case behavior, date leap boundaries, boolean/integer separation, signed-64-bit endpoints, absent optionals and duplicate matching keys produce exact expected IDs/versions |
| FS-06 references | Non-queryable historical references block hard delete; unreadable reference denies whole readback without ID leakage; inactive-readable subject retained but fresh attachment denied; existing readable location needs no lifecycle flag and reads as active |
| FS-07 atomic/replay | Two-key failure changes nothing; each write effect creates the exact audit/receipt/domain counts; fresh no-op receipt only; replay zero rows; lost-response retry returns original identities |
| FS-08 concurrent writers | Facet/schedule edit, publish/publish, binding replace/replace, subject inactivation/catalog retirement versus set use deterministic barriers and yield serial outcomes without stale-index windows |
| FS-09 budgets/plans | 1 and 100000 unrelated-owner items plus deep unrelated history preserve candidate-rooted SEARCH plans; VM-step/deadline/byte/101st-resolution failures return no false-complete result or durable trace |
| FS-10 migration | Predecessor fixture with all item types/history backfills exact empty markers, preserves all existing rows/identities, preserves rebuilt audit rows, and rejects old writers; interrupted migration rolls back |
| FS-11 rollback/repair | Consistent backup restore returns pre-migration data; explicit derived-index rebuild matches canonical values; corrupt definition cannot be repaired from index; missing/drifted schema object fails preflight |
| FS-12 work integration | Queued, leased/in-progress, retry and terminal work follow logical Section 5's verified-retention rule across multiple facet edits; unchanged schedule semantics and no duplicate send; executable proof still required |
| FS-13 flight proof | Register -> bind -> create item -> attach -> inspect -> query -> replace -> retire/remove through public commands; failed attach leaves separately created item intact |

Additional gates: assert no full integrity/quick/FK scan during routine facet preflight;
reads perform no canonical writes; snapshot consistency plus fresh authorization release
holds; cursor tampering/expiry/source changes fail per logical Section 11.
Also prove system-owner item queries fail validation while system-owned schema
creation/listing remains structurally valid. These decisions are settled below;
permission and cursor behavior still require real runtime proofs, not fake success stubs.

## 13. Confirmed scope and remaining implementation gates

**Operator-confirmed decisions (2026-09-24):**

1. Location references require existence and applicable read permission, not a new
   lifecycle. Subject references retain active-on-authoring/inactive-history rules.
2. Item query ownership is subject or subject_group only. Schema catalogs may still
   be system-owned; catalog ownership does not determine matching items or visibility.
3. Logical Section 9's initial scope is confirmed: scalar fields, same-owner bindings,
   optional facets, item/series-level values and two-command initial authoring. The
   logical owner records this confirmation; that confirmation alone did not ratify
   a physical layout.

**Physical design ratified (2026-09-25):** The operator accepts this v1.0 hybrid layout:
relational identity/history and reference integrity, canonical JSON definitions and
versioned values, and derived current-only typed indexes. The bounded buildability
audit returned one minor response-owner clarification, subsequently patched with a
negative fixture and local regression checks. This acceptance is not a new reviewer
verdict, implementation authorization or closure of the remaining engineering gates.

**Engineering gates (not requests to build more product):** codify the exact
DDL/object manifest/migration fixtures; implement and verify logical Sections 5, 6.1
and 11's work continuity, permission resolvers and authenticated cursor/source-snapshot
rules; map FS fixtures to executable
tests and verify every item-version producer. Capacity/response error mappings must
agree with the owning adapters. No new runtime capability until these gates close.

This specification deliberately does not decide field ACLs, richer value types,
live external observations, recipes, occurrence-level facets, pack-v2 installation, cross-ledger
queries, retention/erasure or a general storage redesign.
