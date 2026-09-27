# Versioned facet commands — trusted-local operator guide

Runtime 0.8.0, ledger schema 17. Implements SPINE-028 on the
[storage foundation](FACET_STORAGE_IMPLEMENTATION.md). The authority remains
[archetype-facets.md](../specs/archetype-facets.md),
[its storage leaf](../specs/archetype-facet-storage.md), and the
[command registry](../contracts/archetype-facet-contract-registry.v1.json).

## Scope

The CLI and importable shared handlers implement eleven commands. They retain the
existing trusted-local/full-scope posture, not web authentication or permission
enforcement. The original web allowlists are unchanged; SPINE-029 adds a separate
[permission-enforced facet API](FACET_WEB_API.md).
Frozen schedule, agenda, rendering, and compact-response payloads are unchanged.
Facet values are descriptive item/series facts, not new scheduling anchors, primary
locations, notification policies or automatic workflow triggers.

| CLI command | Contract version | Purpose |
| --- | --- | --- |
| `facet_schema create/publish/retire/show/list` | `spine.facet-schemas.v1` | Owner-local schema roots and immutable revisions |
| `item_archetype facet_binding set/remove/list` | `spine.archetype-facet-bindings.v1` | Pin an optional named facet to an exact schema revision |
| `item facets update/show` | `spine.item-facets.v1` | Replace/remove values atomically; inspect current or historical snapshots |
| `item facets query` | `spine.item-facet-query.v1` | One typed equality predicate in an explicit adopted item-owner scope |

Invoke using the checkout-local `spine-command --db PATH --input REQUEST.json`.
The command words follow those options. Requests are closed JSON objects. Read the
[request schemas](../contracts/schemas/archetype-facet-commands.schema.json) and
[response schemas](../contracts/schemas/archetype-facet-responses.schema.json) for
exact envelopes. Versions, limits and integer values are decimal strings.

## Authoring flow

1. Use existing commands to establish an owner and event/task archetype.
2. `facet_schema.create`: provide that owner, a unique `schema_key`, and a complete
   definition. Supported scalars are text, enum, boolean, integer, date and subject/
   location reference. No arbitrary JSON Schema, formulas, arrays or remote references.
3. `item_archetype.facet_binding.set`: provide the archetype, `facet_key`, exact
   `facet_schema_revision_id`, and `expected_binding_id` (null for first binding).
   The catalogs must have the same owner and intersecting compatible item types.
4. Create the event/task with its archetype through the existing scheduling commands.
5. `item.facets.update`: use its current `expected_item_version` and 1–8 changes.
   A `set` supplies `facet_key`, `expected_binding_id`, exact schema revision and the
   **complete** values object. A `remove` supplies only its operation and key.
   Omitted optional fields are removed; null is not a field value. Each fresh set
   checks the item's concrete type against both pinned definitions.
6. `item.facets.show` verifies the snapshot, pinned definitions, source receipts and
   reference states. `item.facets.query` finds matching current adopted-owned items;
   participant roles or archetype catalog ownership are not item ownership.

All writes also require unique `command_id`, `actor_subject_id`, and whole-second
`action_timestamp_utc`. Reuse the same command ID after a lost response. Compatible
replay returns the stored effect/IDs with `replayed=true`, `changed=false`, and writes
nothing. Changed writes create one audit and one receipt; no-ops create only a receipt.

Initial item creation and facet attachment are two separate atomic commands. If
attachment fails, the item still exists. There is no create-with-facets composite.
Publishing does not rebind or upgrade existing values. To upgrade, publish, explicitly
replace the binding, then set the item's values against the new exact revision.
Retirement prevents fresh attachment but preserves historical reads and removal.
Clear facets before changing an item's archetype. No per-occurrence facets exist.

`--dry-run` supports every facet write and adds `dry_run=true`, including failures.
It executes a bounded transaction and touched-set validation, then rolls it back;
it does not copy the ledger, persist any rows or send anything. A preview therefore
requires a writable connection and briefly acquires the writer lock. It is not a
reservation. Commit with the same request/ID after reviewing the would-be receipt.

## Protected cursor configuration

All three paginated reads require configuration, **including first pages**. Show
commands and writes do not require it. Provision a private regular JSON file, owned
by the invoking OS user or root, mode 0600 (0400 is also readable); symlinks and
group/world permissions are rejected. Set `SPINE_FACET_CURSOR_CONFIG` to its path.
The file contains exactly:

```json
{
  "secret_hex": "<at least 32 cryptographically random bytes, lowercase hex>",
  "cursor_ledger_id": "<persistent random identifier for this ledger deployment>",
  "cursor_generation": "<persistent random generation identifier>"
}
```

Generate these values with an OS cryptographic random source, outside model/request
JSON. Never use the public test-vector key. Do not put the secret in request files,
logs, Git or chat. Reads never generate or persist keys. This configuration authenticates
cursor integrity, **not the executor or human**.

Use a distinct key/context for clones. Rotate generation after restoring a backup.
Restarting with unchanged configuration preserves continuation; replacing the key
invalidates its MAC. List/query defaults are limit 25 (maximum 100), TTL 900 seconds,
at most 100 total candidates/resources. This is a total-candidate ceiling, not a way
to page arbitrarily large scopes. Capacity errors return no partial result.

Changing query/limit/route invalidates a token. Relevant catalog, item-version or owner
changes make it stale. A concurrent first-page source change fails `environment_failure`;
a continuation fails `stale_cursor`. Reissue a first-page request, rather than editing
the token. Reads write no receipts or cursor cache. The shared request budget covers
source evaluation and release revalidation: no hidden reconstruction retry.

## Notification continuity

Facet-only changes copy canonical supporting facts, then compare scheduling meaning
inside the transaction. A mismatch fails and rolls back. No expansion, materialization,
lease changes, work cancellation, attempts or sending occurs. Existing work remains
keyed to its historical policy/version; the worker resolves current policies by stable
item/intent and verifies semantic continuity before attempts, across successive edits.

`reconciliation_performed=true` means a committed changed update verified retention
where policies or reminder work exist. It does not mean delivery or created work.
No-op, replay and preview return false. Already stale work is not revived. A source-event
facet edit still increments its version and makes dependent follow-source bindings stale;
use their existing reconciliation flow. Bound-target facet edits preserve unchanged due
anchor meaning. Existing attempts/renderings remain historical evidence.

## Verification and remaining boundary

Public runtime tests: `test_facet_commands.py`, `test_facet_runtime_reads.py`.
They cover all six write previews/replays, multi-edit work retention, recurrence and
follow-source behavior, atomic failure, owner-scoped queries, signed cursor failures,
first-page/continuation source races, writer contention and no read evidence.
`test_facet_plans_concurrency.py` also exercises the public owner-rooted query with
100000 unrelated items and 10000 unrelated historical versions. Storage and all-writer
tests remain in force; the new producer is included in the packaged writer inventory.

SPINE-029 implements permission resolvers, protected reference disclosure,
account-bound cursors, a dedicated web registry and permission-race tests. Only its
explicit routes may expose facets; do not add bypass aliases. Deployment, migrations
against a live ledger, commit and push remain operator-controlled actions.
