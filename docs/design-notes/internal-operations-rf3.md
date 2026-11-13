# RF3 — synchronous mutation-effect propagation

Status: first binding increment implemented and verified, uncommitted (2026-11-13).
This is implementation evidence, not a new normative contract or full RF3 closure.
The authoritative boundary is
[internal application operations §7](../../specs/internal-application-operations.md).
Current scope/status lives in [SPINE-101](../BACKLOG.md#spine-101--rf3-synchronous-mutation-effect-propagation).

## Baseline and preservation

The operator requested committing the verified manual R2 increment, then starting
RF3. The R2 checkpoint is `7f35d68`; R3 automatic scheduling/attempt integration,
public activation, deployment and push are not selected by this increment.

Two unrelated changes were excluded from that commit and remain untouched:

- `AGENTS.md`: SHA-256 `fa4b49c7fcad79cf0e94c70fd5ee4b7dc55ab8c6a3987371577214edbe8e4570`.
- `docs/design-notes/recurring-related-task-r2-restoration.md`: SHA-256
  `3fd7bee35e9834aaa9905aa70c2ed7f45dc8c6a9afccec39fc131bb768e26a76`.

The frozen RF1 catalog, RF2 child composition and explicit R2 amendment witnesses
are not recaptured or rewritten for RF3. Existing receipts, identities, work modes,
audit order and catalog increments must continue matching those witnesses.

## First increment: closed binding inventory

The three native persistence writers remain in `ledger/temporal_bindings.py`:
`insert_temporal_binding`, `insert_temporal_binding_revision`, and
`retire_temporal_binding`. Each now requires an owned transaction and records exact
before/after binding facts in the transaction's propagation component. Header plus
first revision, or successor revision plus retirement, coalesce into one logical
effect before propagation.

| Existing composer | Native writes | Existing consequence now centrally applied |
| --- | --- | --- |
| `commands/temporal_bindings.handle_related_task_create.insert_bundle` | Header + first revision | One binding catalog increment |
| `commands/temporal_bindings._manual_reconcile` | Revision, optional retirement | One increment only when truth changed |
| `commands/temporal_bindings._versioned_reconcile.extension` | Revision, optional retirement | One increment |
| `services/recurring_task_children._create.extension` | Header + first revision | One increment |
| `services/recurring_task_children.change.extension` | Revision, optional retirement | One increment |

`core/mutation_effects.py` defines frozen binding snapshots/effects and proven
`BINDING`/`TIME` categories. A revision or item-version advance alone does not prove
a time change. `ledger/mutation_effects.py` captures exact IDs, versions, revision,
status and temporal facts. Existing bindings use an indexed before-read; successful
native writes project their exact inserted values, coalescing intermediate writes
without rereading them. New header/revision pairs need only one persisted snapshot
read at propagation. The ledger never calls the application layer.
`services/mutation_propagation.py` validates the pending effect against persisted SQL,
applies the existing catalog primitive exactly once, checks its increment and only
then acknowledges the obligation. Effects are private transaction facts, not public
`changed_dimensions`, durable events or an extensible event bus.

The transaction owner checkpoints/restores/resets propagation obligations together
with existing state. Unacknowledged effects fail finalization. No-op/replay paths
produce no new obligation or consequence. Incomplete, stale, duplicate or omitted
propagation fails closed; failure later in the same transaction rolls back both
the binding and its consequence. Neither propagation nor its persistence helpers
commit, dispatch commands, materialize work, schedule repair or send notifications.

## Consequence ownership retained; remaining RF3 work

The new owner does **not** repeat consequences already applied elsewhere:

- `temporal_binding_catalog_related_item_audit` in migration
  `0008_relative_temporal_bindings.sql` advances the binding catalog on relevant
  source/target item audits. It excludes the named binding/related-task audits
  already paired with explicit increments. Ordinary source edits therefore still
  have their own catalog increment, separate from later binding reconciliation.
- `ledger/ownership.advance_ownership_epoch` retains its existing epoch ownership
  and transaction-local once-consumption rule.
- `ledger/facets` retains typed-index/continuity checks and finalization, including
  the existing temporary tracking machinery.
- `ledger/rendering_definitions.finalize` retains rendering, presentation and
  catalog consequences. The relative order of recurring, rendering and facet
  finalizers is unchanged.

These are retained owners, **not a claim that every remaining writer has been
inventoried or migrated**. Next RF3 work must close the ordinary item, recurrence,
relation, ownership and policy writer/effect inventory, then integrate their
existing consequences through the accepted typed boundary without duplicating
trigger/finalizer behavior. Include lower-level and recurring paths, exact
before/after witnesses and missed-propagation guards. No R3 dirty queue, new
attempt semantics or global eager reconciliation belongs in RF3.

## Verification

- Initial affected binding, recurring child, transaction-state and R2 preservation
  selection: 52 tests passed.
- Focused propagation/state/frozen-witness/dependency selection: 34 tests passed.
- New regressions cover exact categories, catalog cardinality, no-op/replay,
  omitted application propagation and omitted catalog consequence, duplicate
  propagation, nested rollback/retry, later finalizer failure, owned-transaction
  enforcement, context-manager commit checks, and raw commit rejection.
- AST inventories pin all native Python binding SQL writers and their composer
  call counts; dependency checks include the three new modules.
- Seven propagation/persistence/state/child-operation modules pass focused static
  typing. An expanded check including the legacy command module reports 37 typing
  errors; a `--shadow-file` check of the committed `7f35d68` command module confirms
  the same 37 diagnostics (the replaced increment call becomes the propagation
  call). This is retained command-module typing debt, not a clean whole-command
  typing claim or a new RF3 cleanup scope.
- Final focused propagation/dependency/operator-documentation/declaration/web-copy
  selection: 32 tests passed. Focused Ruff, 387 local documentation link targets,
  diff hygiene and preserved-file/frozen-witness hashes pass.
- The first full run found one real regression (1,546 tests, one failure, one
  skipped): redundant snapshot reads pushed delayed-rdate reconciliation beyond
  its unchanged 100,000-instruction budget. Native-value capture now eliminates
  those intermediate reads while preserving the final SQL equality check. No
  budget was increased or disabled. The 24-test edge/propagation/frozen-witness
  selection passes, including the original seven-task case, a one-snapshot-read
  assertion and deliberate captured-value mismatch rollback.
- After that optimization, the 35-test transaction/preservation/documentation/
  declaration/web-copy selection and seven-module static typing pass again.
- Final full suite: **1,548 tests, OK (one skipped)**, 415.285 seconds, using
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
  and installed pinned Tickerd (no sibling source import). Final focused Ruff,
  typing and diff checks pass. This binding increment is verified and uncommitted;
  the remaining RF3 inventory/integration above is still open.
