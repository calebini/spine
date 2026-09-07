# Spine Ledger Instance Identity

Status: Implemented by this working change; Spine 0.5.0 / schema 14
Contract: `spine.ledger-instance.v1`
Date: 2026-09-07

## 1. Authority and threat model

Every initialized current ledger contains exactly one immutable, Spine-owned
`ledger_instance_id`. It identifies the ledger lineage independently of filename,
host, process, web service configuration, selected account, and item IDs. Clients
can record this ID and compare it before targeting a ledger. A mismatch must stop
that client's workflow rather than silently accepting a new target.

This is accidental-target detection, NOT authentication, authorization, a secret,
proof of physical database identity, anti-tampering, or clone detection. A principal
with unrestricted database access can bypass SQLite triggers. Ordinary backup copies
intentionally have the same ID; this contract does not coordinate writes across copies.
No new authenticated remote interface, replication, installer, reset, or fork tool is
introduced. Existing mutation commands do not acquire an implicit expected-ID field;
clients remain responsible for comparison and connection/target continuity.

The existing web `ledger_access_state.ledger_id` remains a separately provisioned
access namespace. It and account bindings, grants, receipts, and web request/cursor
contracts are not renamed or rebound. A web ledger ID is not a substitute for this
instance ID, and web provisioning is not required to obtain an instance identity.

## 2. Authoritative metadata

`ledger_instance_metadata` has one row:

- `singleton`: SQLite integer 1, primary key;
- `identity_contract`: `spine.ledger-instance.v1`;
- `ledger_instance_id`: `ledger_instance_` followed by exactly 64 lowercase hex digits;
- `origin`: `initialized_random_v1` or `schema13_logical_backfill_v1`.

CHECK/unique constraints restrict shape; triggers reject UPDATE, DELETE and a second
INSERT, including INSERT OR REPLACE. Schema-object fingerprints include this table
and all three triggers. No public command changes any of these fields. There is no
mutable last-seen timestamp or per-read persistence.

## 3. Initialization and deterministic migration

Fresh initialization generates 32 cryptographically random bytes using the platform
random source and renders them as the 64-digit suffix. Identical fresh empty ledgers
receive independently generated identities. Initialization on an existing current
ledger validates and retains its identity; it MUST NOT generate a replacement.

Migration 13 → 14 uses deterministic logical backfill, not a path, host, wall clock,
web namespace, or a freshly generated random seed. Under BEGIN IMMEDIATE, before
schema-14 DDL or migration-history changes, hash the schema-13 snapshot below. Older
ledgers first cross their existing migrations to schema 13; the input is the state
at that boundary, including those migrations' recorded timestamps.

The exact `schema13_logical_backfill_v1` algorithm is:

1. Start SHA-256. Each input value is serialized as JSON with ASCII escaping, compact
   separators, no nonfinite JSON numbers, and no Unicode normalization. Prefix those
   ASCII bytes with their byte length in unpadded decimal ASCII followed by `:`.
   Concatenate framed values without other delimiters.
2. Feed string `spine.ledger-instance.schema13-logical.v1`.
3. Select sqlite_schema rows with non-null SQL and names not matching case-sensitive
   `sqlite_*`, ordered by type then name with BINARY collation. For each feed the array
   `["object", type, name, tbl_name, sql]`. DDL text is exact, not normalized.
4. For each selected table in BINARY name order, use columns in `table_xinfo` order.
   Feed `["table", name, column_names]`. Select those columns ordered, for each column
   in turn, by `typeof(column)` BINARY then its value BINARY. Virtual tables fail with
   `ledger_instance_backfill_unsupported`; they require explicit migration review.
5. For each row feed `["row", encoded_cells]`. Cells are arrays: `["null"]`,
   `["integer", decimal_string]`, `["real", Python_float_hex_string]`,
   `["text", exact_string]`, or `["blob", lowercase_hex]`. Real zero normalizes to
   positive zero before hex encoding so equal SQL sort keys cannot reorder signs.
   Then feed `["end_table", decimal_row_count]`.
6. The ID is `ledger_instance_` plus the lowercase SHA-256 digest.

This is a dedicated framed logical-snapshot encoding, not Spine canonical JSON:
it explicitly preserves SQLite storage classes and arbitrary stored Unicode/blob data.
Ordinary extra user tables/objects participate in the snapshot; sqlite internal
indexes, sequences and statistics do not. Row insertion order, rowids not declared as
columns, file location, WAL layout and new migration time are not inputs. DDL text,
declared integer primary keys, prior migration times and user data are inputs.

Byte-equivalent logical preimages produce the same ID, including independently
migrated copies and independently created identical pre-schema-14 empty ledgers.
Different identity for an intentional fork is NOT supported by this release. Do not
edit metadata or delete it to manufacture a fresh identity. Creating a genuinely new
empty ledger through initialization is different from forking existing data.

DDL, identity insert and schema-14 migration-history insertion commit atomically.
Failure rolls back this entire step. Retry from the same schema-13 state derives the
same result. Earlier migration steps may already have committed and retain their own
existing recovery rules. Failure before any fresh identity commit has exposed no ID.

Backfill is an explicit, potentially expensive offline migration: it reads all user
table data and may use SQLite temporary sort storage. Quiesce writers, ensure backup
and temporary-storage headroom, and allow migration time proportional to ledger size.
Application memory streams rows rather than materializing the full ledger. No routine
read, worker tick, service startup, or command recomputes this digest.

## 4. Readback and fail-closed admission

`system.info` now returns `spine.system-info.v3`, adding required top-level
`ledger_instance_id` to v2 facts. Its request stays `{}`. Frozen v2 schema remains
historical; the generic response-schema path selects v3. The compiled registry
requires `spine.system-info.v3`, `spine.ledger-instance.v1`, canonical JSON and the
unchanged Tickerd compatibility capability. Do not advertise v2 as the emitted shape.

After object validation, routine ledger preflight reads at most two metadata rows
and checks singleton, contract, ID syntax and origin. Missing, malformed, or multiple
rows fail `ledger_instance_invalid`; no read path repairs metadata. Direct system.info
handler failure is `environment_failure` with field `ledger_instance_id`; CLI startup
may reject sooner through its existing preflight error envelope. Worker failure emits
one `ledger_runtime_preflight_failed` diagnostic with reason `ledger_instance_invalid`,
DOWN/not-ready, nonzero halt, supervisor-only retry, and no processing. Existing schema
object mismatch behavior takes precedence if DDL itself is missing or changed.

Deep verification and migration (including --no-verify's postcondition) also require
valid identity. Shape validation cannot prove the original ID has not been replaced
by an administrator; comparing a previously trusted external ID is the client's job.

## 5. Backup, restore and compatibility

Consistent SQLite backup/restore, moving a database, restarting, VACUUM and ordinary
migrations retain metadata unchanged. Restoring an older snapshot from the same
post-identity lineage retains its ID even if domain state moves backward. Restoring
a pre-identity backup reruns the deterministic rule against that older snapshot and
need not reproduce an ID derived from a later pre-identity snapshot. Preserve the
post-migration backup and recorded ID for reliable lineage checks.

Runtime 0.5.0 requires schema 14. Rollback requires a matched previous runtime and
pre-migration database backup; old runtime must not be run against schema 14. Tickerd
provider requirements are unchanged. Clients pinned to system-info.v2 must upgrade to
v3 explicitly. The current trusted web API and provisioning namespace are unchanged.

## 6. Verification

`tests/test_ledger_identity.py` covers independent initialization, reopen/idempotent
initialization, deterministic backfill despite insertion/migration-time differences,
data-sensitive derivation, immutable metadata, migration rollback/retry, backup and
VACUUM preservation, missing/malformed identity, worker no-processing and frozen v2.
Existing migration, system-info, bounded-preflight and full regression tests remain
release gates. No successful read creates a command receipt or identity repair write.
