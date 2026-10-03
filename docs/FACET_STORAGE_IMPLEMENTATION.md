# Facet storage foundation — SPINE-027

Implementation handoff, 2026-09-27. This records engineering evidence; it does not
override [the logical contract](../specs/archetype-facets.md),
[accepted storage design](../specs/archetype-facet-storage.md), or
[Spine-wide atomicity](../specs/STORAGE_ATOMICITY_SPEC.md).

## Schema 18 location freeze — SPINE-038

Runtime 0.8.3 extends the existing location canonical-field trigger to every persisted
facet reference, including historical and non-queryable fields. No new tables or
indexes: the trigger uses `item_facet_references_location_idx`. The only durable
migration changes are the trigger definition and the schema-18 version row. The
schema-17 manifest is retained for exact predecessor verification.

Stop all writers (worker, web service and direct CLI), take a consistent verified
SQLite backup including WAL state, and run the checkout-local `spine-ledger-migrate
--db <ledger>` before restarting the new runtime. Do not copy a live main file alone
or remove sidecars. Routine commands/worker startup reject schema 17 until migration;
older code rejects schema 18. Migration failures roll back the trigger and version
atomically. For rollback after a successful upgrade, stop writers and restore the
verified pre-migration backup with matching old code; do not decrement the version or
manually drop the protection. Restoring that backup discards post-upgrade writes, so
preserve the failed deployment ledger separately for reconciliation first.

Existing canonical values are frozen as they stand at cutover; earlier label values
cannot be recovered from reference IDs. Corrections create a new location and a new
item version referencing it. Metadata-only edits remain allowed. Removing a current
facet does not unfreeze locations still referenced by history. Notification work and
attempt bodies are not rewritten; facet-aware message rendering remains unimplemented.

FS-14 coverage: [location-freeze tests](../tests/test_facet_location_freeze.py) exercise
facet-only/non-queryable history, metadata, correction, both writer-lock orderings,
indexed lookup, populated migration parity, interrupted DDL/activation, backup restore
and schema drift. Existing primary-location and multi-policy notification migration
tests cover retained behavior. These are local disposable-ledger tests, not a deployment.

Verification checkpoint: 776 tests and 1104 subtests passed; strict mypy on 43 source
files, Ruff, compilation, contract-package synchronization and link/diff checks passed.
A non-editable 0.8.3 wheel installed outside the checkout passed fresh initialization,
17-to-18 migration and deep verification; its current manifest differs from schema 17
in exactly the location trigger fingerprint. No staging ledger was used.

## Delivered boundary

Slice A (development runtime 0.6.2) / ledger schema 16 delivered the eight-table hybrid layout, immutable
canonical definition/value decoding, historical references, current-only typed
indexes, and complete snapshots for every existing version producer. At that checkpoint
public facet contracts were unadvertised. The subsequent runtime 0.7.0 command slice
is documented in [FACET_COMMANDS.md](FACET_COMMANDS.md); SPINE-029 subsequently adds
the dedicated [facet API](FACET_WEB_API.md) in runtime 0.8.0/schema 17.
The evidence below records the storage checkpoint, not later-slice closure.

The [closed writer inventory](../src/spine/ledger/facet_writer_inventory.v1.json)
records actual allocation call sites, the common finalizer, coverage test and
maintenance path. Project/collection have no ordinary version-producing command
today; migration still backfills every historical version of those types.

`LedgerConnection` installs connection-local tracking triggers (no durable tracking
table). The common allocator registers every allocated version. Before outer commit,
the finalizer checks all tracked versions, current item projections, touched catalog
roots/bindings and definition projections. Missing markers, omitted finalization,
omitted allocations and projection mismatches roll back. Raw SQL `COMMIT` or an
outermost savepoint release cannot bypass this connection's finalizer. Savepoints
must be nested inside the owned transaction; owner-scope discovery receives an outer
read transaction for that reason. This is an implementation-integrity boundary,
not access control against an operator with direct SQLite/file access.

CLI writes now use the shared outer transaction, including receipts written after
item helpers. Web requests reuse their existing outer transaction. Internal item
helpers acquire `BEGIN IMMEDIATE` when not already inside that boundary. Callers
must use `spine.ledger.connect`; code composing operations must use
`LedgerConnection.atomic_command`, not an unmanaged pending transaction. Storage
primitives never commit or generate command/audit identities on their caller's behalf.

`ItemVersionDraft.facet_entries` is an internal storage primitive: omission copies
the exact prior snapshot; an explicit empty tuple removes it. It is **not** a public
request field or a substitute for Slice B's command authorization, receipt/audit
derivation and notification-continuity work. Existing ordinary commands retain
facets and original authoring provenance without requalifying retired catalogs or
inactive references.

The existing non-facet command preview still uses an in-memory ledger copy; it now
uses the same facet-aware connection and FK enforcement. This slice does not claim
to implement the future bounded facet dry-run contract.

## Verification map

| Family | Persisted proof in this slice | Remaining gate |
| --- | --- | --- |
| FS-01 | `test_facet_storage.py`: published normalization/hash vector persisted byte-exact; malformed JSON, duplicate keys, surrogates, decoder selectors, NFC and byte/domain bounds | Public schema commands/no-op receipts in SPINE-028 |
| FS-02 | `test_facet_storage.py`: owner-local keys including retired system roots, active binding uniqueness, contiguous revisions, immutable rows, composite root/binding/typed-field FKs | Public command error precedence in SPINE-028 |
| FS-03 | `test_facet_storage.py`: publish, binding replacement/retirement, schema retirement and inactive references preserve old bytes/provenance and decoding | Permission-sensitive public hydration in SPINE-029 |
| FS-04 | `test_facet_writers.py`: source inventory reconciled with allocation sites, every producer executed on empty and eight-entry snapshots; `test_facet_storage.py`: last removal, 256 references/index rows, missing marker/finalizer/touch, multi-item rollback, raw commit rejection | New producers must extend inventory and executable coverage |
| FS-05 | `test_facet_storage.py`: typed flight/location/date/enum/boolean/integer probes, case sensitivity, absent fields and signed-64-bit limits | Public query result assembly/pagination in SPINE-028/029 |
| FS-06 | `test_facet_storage.py`: all reference fields have historical FK protection; existing location accepted without invented lifecycle; inactive subject rejected for fresh attachment but retained historically | Unreadable-reference non-disclosure and authorization in SPINE-029 |
| FS-07 | `test_facet_storage.py`: multi-key/commit failures roll back; CLI missing marker returns environment failure with no item/audit/receipt; existing-command replay/preview regression scenarios run with seeded facets | All six new public writes' identities, audit counts, replay and bounded dry-run in SPINE-028 |
| FS-08 | `test_facet_plans_concurrency.py`: real two-connection writer lock and read snapshot; stale item/catalog/binding comparisons; inactivation/retirement serialized before fresh set | Facet-edit versus work lease/attempt races in SPINE-028; permission races in SPINE-029 |
| FS-09 | `test_facet_plans_concurrency.py`: indexed text/integer candidate probes with 100000 unrelated-owner items and 10000 unrelated versions; VM interruption leaves no durable trace; codec/SQL bounds | Shared public deadline/bytes/101st resource resolution and cursor failures in SPINE-028/029 |
| FS-10 | `test_facet_migration.py`: predecessor all types/history, exact empty backfill, prior rows/identities and extra audit objects preserved, DDL/data rollback, fresh/migrated DDL parity, old-runtime rejection | Deployment remains a separate operator action |
| FS-11 | `test_facet_migration.py`: consistent backup/restore; `test_facet_storage.py` and `test_facet_plans_concurrency.py`: explicit index rebuild, corrupt authority cannot be repaired from indexes, bounded preflight versus deep verification; existing preflight tests cover DDL drift | No automatic down-migration or general repair service |
| FS-12–13 | Not claimed | Notification continuity and the public end-to-end flight scenario in SPINE-028/029 |

The writer harness reuses real existing command tests while seeding initial persisted
snapshots without changing item version numbers. It then compares every historical
snapshot and original evidence. This is not just a manifest-presence or pure-oracle test.

## Migration and operations

No staging database was touched. Deployment must stop all writers, take a consistent
SQLite backup using the established procedure, and run the explicit migration tool.
Schema 15 admission includes its packaged predecessor object manifest and deep
verification even when the overall migration invocation disables optional final
verification. Schema 16 creation, audit CHECK rebuild, historical marker backfill,
parity/FK checks and version advancement share one transaction. Earlier migrations
in a chain keep their existing separate transaction boundaries.

Routine command/worker preflight remains schema-object/contract bounded. Only
explicit deep verification scans all facet history. Post-commit rollback means
stopping writers and restoring the verified schema-15 backup with its matching
runtime; do not run an old binary against schema 16 or drop facet tables to downgrade.

## Verification limits

The full local suite passes **701 tests and 930 subtests**. Ruff, compileall, focused
typing and local documentation links pass. Source specifications and public machine
contracts were not rewritten by this implementation.

The new core/storage/transaction modules pass focused strict type checking. The
repository-wide strict mypy run reports typing/stub diagnostics across the
command, web and dependency modules; no repository-wide type-clean claim is made.
Wheel construction could not run in this venv because `setuptools.build_meta` is
unavailable. Package-data declarations include the migration, both object manifests
and writer inventory; installed-wheel verification remains a packaging-environment
check, not a claim established by source tests. No Whetstone run, commit, push or
deployment is part of this implementation.
