# Spine Storage and Atomicity

Status: Draft v0.1 — authority consolidation; no runtime or schema change
Date: 2026-09-24
Scope: Spine-wide persistence ownership and delegation to feature storage leaves

## 1. Authority

This document is the Spine-wide persistence/atomicity owner. It consolidates the
existing boundaries in [architecture](architecture.md), [ontology](ontology.md),
and the [command contract](agent-command-contract.md); it does not replace their
domain semantics, replay identities, error precedence or feature-specific rules.
It was introduced with the facet-storage draft because no document at this path
previously existed. It is not a claim that a new storage engine has been implemented.

Feature leaves specify their physical tables, constraints, indexes, migration and
verification requirements. [Archetype facet storage](archetype-facet-storage.md)
owns those details for facets; [archetype facets](archetype-facets.md) retains logical
authority. In a conflict, do not implement a leaf as an implicit change to its parent
or logical owner: reconcile the owning contract explicitly first.

## 2. Shared persistence boundary

- One canonical SQLite ledger owns coordination truth. Derived indexes and external
  projections are not alternative authorities.
- Writers enable foreign-key enforcement. A command's canonical rows, supporting
  sets, derived indexes, audit and receipt commit atomically or roll back together.
  Required side-effect attempt persistence remains owned by the notification/adapter
  contracts; database atomicity cannot roll back an external send.
- One outer command transaction owns commit/rollback. Nested helpers must not commit,
  open an independent writer, or execute scripts that implicitly end the transaction.
  See the existing [transaction boundary](../src/spine/ledger/transactions.py).
- Recheck current versions, replay identity and required authority inside the write
  transaction. Serialization alone does not excuse an omitted stale-version check.
  The owning command defines successful no-op/replay behavior and validation ordering.
- Immutable history is not rewritten by current catalog changes or index repair.
  A derived index is changed in the same commit as the canonical facts it represents.
  Missing/corrupt canonical history must not be repaired by guessing from that index.
- Routine preflight remains bounded schema/contract admission, not a full integrity,
  foreign-key or historical-invariant scan. Deep verification is the explicit
  operator/migration path defined by the command contract. Feature reads and failed
  preflight do not write durable records or perform opportunistic repairs.

## 3. Migration and operational boundary

Migrations use the existing ordered migration machinery and exact schema-object
manifest discipline. Feature implementation must publish matching schema-version,
packaged-manifest and migration tests before activation. A draft does not reserve the
next global schema number. Older writers must reject a newer unsupported schema.

An operator-approved migration may do ledger-size-dependent work while writers are
stopped; ordinary startup must not inherit that work. Verify a consistent backup and
restore path before a destructive or incompatible migration. Never describe an old
binary's ability to open a file as permission to write its newer schema. Rollback
instructions must distinguish transaction rollback, binary rollback and restoring
data from a pre-migration backup, including loss of subsequent writes.

The [operational-resilience specification](operational-resilience.md) retains its
resource and failure-containment authority and existing implementation/deferment
status. This consolidation does not reopen the deferred storage-retention or general
qualification initiatives. Feature-local budgets and verification still apply.
